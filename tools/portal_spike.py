"""Spike: drive the ScreenCast portal by hand and measure what `gst-launch-1.0` can read from it.

Run it on a Wayland session and click the sharing dialog when it appears (twice: once with the cursor
embedded in the video, once asking for cursor metadata):

    uv run --with jeepney python tools/portal_spike.py

It prints the portal's `Start` results, the frames and CPU `gst-launch-1.0` used over 10 seconds, and
every `cursor` line GStreamer logged when the cursor mode is metadata.
"""
from __future__ import annotations

import os
import resource
import subprocess
import time
import uuid

from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
from jeepney.io.blocking import Proxy, open_dbus_connection

PORTAL = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
SCREENCAST = DBusAddress(PATH, bus_name=PORTAL, interface="org.freedesktop.portal.ScreenCast")
SECONDS = 10


def request(conn, method: str, signature: str, args: tuple, options: dict) -> tuple[int, dict]:
    """Call a portal method that answers with a `Response` signal, and wait for that signal."""
    token = "spike" + uuid.uuid4().hex[:8]
    sender = conn.unique_name[1:].replace(".", "_")
    path = f"{PATH}/request/{sender}/{token}"
    rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=path)
    Proxy(message_bus, conn).AddMatch(rule)
    options = {**options, "handle_token": ("s", token)}
    with conn.filter(rule) as responses:
        conn.send_and_get_reply(new_method_call(SCREENCAST, method, signature, (*args, options)))
        message = conn.recv_until_filtered(responses, timeout=120)
    code, results = message.body
    return code, results


def start_session(conn, cursor_mode: int) -> tuple[str, int, int, tuple[int, int]]:
    """Open a monitor session; return its handle, the PipeWire fd, the node id and the stream size."""
    _, created = request(conn, "CreateSession", "a{sv}", (), {"session_handle_token": ("s", "spike" + uuid.uuid4().hex[:8])})
    session = created["session_handle"][1]
    request(conn, "SelectSources", "oa{sv}", (session,),
            {"types": ("u", 1), "multiple": ("b", False), "cursor_mode": ("u", cursor_mode)})
    code, started = request(conn, "Start", "osa{sv}", (session, ""), {})
    if code != 0:
        raise SystemExit(f"Start answered with code {code} (1 means the dialog was cancelled)")
    print("Start results:", started)
    node, props = started["streams"][1][0]
    size = tuple(props["size"][1])
    reply = conn.send_and_get_reply(new_method_call(SCREENCAST, "OpenPipeWireRemote", "oa{sv}", (session, {})))
    fd = reply.body[0]
    return session, (fd.to_raw_fd() if hasattr(fd, "to_raw_fd") else fd), node, size


def measure(fd: int, node: int, size: tuple[int, int], *, debug: bool) -> None:
    """Run gst-launch for a few seconds and print the frame count, rate and CPU time."""
    width, height = size
    command = ["gst-launch-1.0", "-q", "pipewiresrc", f"fd={fd}", f"path={node}", "always-copy=true", "!", "videoconvert", "!",
               "videoscale", "!", f"video/x-raw,format=BGRA,width={width},height={height}", "!", "fdsink", "fd=1", "sync=false"]
    env = {**os.environ, **({"GST_DEBUG": "pipewire:5"} if debug else {})}
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(fd,), env=env)
    received = 0
    while time.monotonic() - started < SECONDS:
        chunk = process.stdout.read(width * height * 4)
        if not chunk:
            break
        received += len(chunk)
    elapsed = time.monotonic() - started
    process.kill()
    _, log = process.communicate()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    frames = received / (width * height * 4)
    cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    print(f"frames: {frames:.1f} in {elapsed:.1f}s = {frames / elapsed:.1f} fps; gst CPU {cpu:.2f}s "
          f"({100 * cpu / elapsed:.0f}% of a core); frame bytes per frame expected {width * height * 4}")
    if debug:
        lines = [line for line in log.decode(errors="replace").splitlines() if "cursor" in line.lower()]
        print(f"gst log lines mentioning cursor: {len(lines)}")
        print("\n".join(lines[:15]))


def main() -> None:
    """Run both measurements and close each session."""
    conn = open_dbus_connection(bus="SESSION", enable_fds=True)
    for cursor_mode, label in ((2, "embedded cursor"), (4, "metadata cursor")):
        print(f"\n== {label}: click the sharing dialog ==")
        session, fd, node, size = start_session(conn, cursor_mode)
        try:
            measure(fd, node, size, debug=cursor_mode == 4)
        finally:
            conn.send_and_get_reply(new_method_call(
                DBusAddress(session, bus_name=PORTAL, interface="org.freedesktop.portal.Session"), "Close"))


if __name__ == "__main__":
    main()
