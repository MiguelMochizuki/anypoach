"""A fake `org.freedesktop.portal.Desktop` on a private session bus, for testing the DBus transport."""
import os
import subprocess
import threading

from jeepney import DBusAddress, HeaderFields, MessageType, message_bus, new_method_return, new_signal
from jeepney.io.blocking import Proxy, open_dbus_connection

NAME = "org.freedesktop.portal.Desktop"
STREAM = (57, {"size": ("(ii)", (640, 480)), "position": ("(ii)", (0, 0)), "source_type": ("u", 1)})


class FakePortal:
    """Answers the ScreenCast calls the client makes and records what the client closed.

    Attributes:
        address: DBus address of the private bus.
        start_code: Response code sent for `Start` (0 success, 1 cancelled).
        emit_before_reply: Send each `Response` signal before the method reply, to catch a client that
            subscribes too late.
        closed_sessions: Handles of the sessions the client closed.
    """
    def __init__(self) -> None:
        self.daemon = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"],
                                       stdout=subprocess.PIPE, text=True)
        self.address = self.daemon.stdout.readline().strip()
        self.start_code, self.emit_before_reply, self.closed_sessions = 0, False, []
        self._stop, self._ready = threading.Event(), threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(5)

    def stop(self) -> None:
        """Stop the service and the bus."""
        self._stop.set()
        self._thread.join(2)
        self.daemon.terminate()
        self.daemon.wait(2)

    def _run(self) -> None:
        conn = open_dbus_connection(bus=self.address, enable_fds=True)
        Proxy(message_bus, conn).RequestName(NAME, 4)
        self._ready.set()
        while not self._stop.is_set():
            try:
                message = conn.receive(timeout=0.1)
            except TimeoutError:
                continue
            if message.header.message_type is MessageType.method_call:
                self._handle(conn, message)
        conn.close()

    def _handle(self, conn, message) -> None:
        fields = message.header.fields
        member, sender = fields[HeaderFields.member], fields[HeaderFields.sender]
        if member == "OpenPipeWireRemote":
            conn.send(new_method_return(message, "h", (os.open(os.devnull, os.O_RDONLY),)))
        elif member == "Close":
            self.closed_sessions.append(fields[HeaderFields.path])
            conn.send(new_method_return(message))
        else:
            options = message.body[-1]
            token = options["handle_token"][1]
            path = f"/org/freedesktop/portal/desktop/request/{sender[1:].replace('.', '_')}/{token}"
            code, results = 0, {}
            if member == "CreateSession":
                results = {"session_handle": ("s", "/org/freedesktop/portal/desktop/session/1")}
            elif member == "Start":
                code, results = self.start_code, ({"streams": ("a(ua{sv})", [STREAM])} if self.start_code == 0 else {})
            response = new_signal(DBusAddress(path, interface="org.freedesktop.portal.Request"), "Response",
                                  "ua{sv}", (code, results))
            reply = new_method_return(message, "o", (path,))
            for item in ((response, reply) if self.emit_before_reply else (reply, response)):
                conn.send(item)
