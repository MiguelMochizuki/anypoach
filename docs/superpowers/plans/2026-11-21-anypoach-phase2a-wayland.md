# AnyPoach Phase 2a (Wayland) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a screen area on a Wayland session (GNOME tested) with the same flow and the same brief as X11 and Windows.

**Architecture:** A `PortalBackend` implements the existing `CaptureBackend` on top of the `xdg-desktop-portal` ScreenCast API. DBus is spoken with `jeepney`. The PipeWire stream is read from a `gst-launch-1.0` subprocess that writes raw BGRA frames to a pipe, and the newest frame is kept for `grab()`. The portal can only share a whole monitor, so the window shows a frozen first frame in a fullscreen widget where the user drags the area, and the crop is ours.

**Tech Stack:** Python 3.11+, `jeepney` (pure Python DBus), `gst-launch-1.0` with `pipewiresrc` (system packages), numpy, PySide6, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-21-anypoach-phase2-design.md`

## Global Constraints

- Python 3.11+, managed with `uv`; `ruff` line length 110; default pytest run is `-m 'not live'`.
- `uv run anypoach` must keep working with no system Python packages: no `PyGObject`; GStreamer is only ever run as a subprocess.
- `jeepney` is a Linux-only dependency (`sys_platform == 'linux'`) and every import of it, and of the portal modules, stays lazy so Windows and macOS CI are unaffected.
- GNOME is the only tested compositor; other compositors are best effort and the README says so.
- Pointer: no global mouse hook, no libei; Wayland trace stays `available: false` (spike confirms, Task 1).
- Privacy (`AGENTS.md`): no network, no telemetry, no persistent retention. The portal `restore_token` is NOT used in this plan; the opt-in lands with the settings screen in phase 2b. The portal session is closed as soon as the recording stops or is cancelled.
- Python docs: Google-style docstrings, module docstring in every module including tests, as written in `CONTRIBUTING.md`.
- Commits: atomic Conventional Commits with a scope (`type(scope): summary`), staged by file name, no AI attribution lines.
- Portal facts: `ScreenCast` interface `org.freedesktop.portal.ScreenCast` at `/org/freedesktop/portal/desktop`; cursor modes Hidden=1, Embedded=2, Metadata=4; source types Monitor=1, Window=2; `Response` codes 0 success, 1 user cancelled, 2 other failure; dev machine is GNOME Wayland with portal version 5.

## Review Focus

1. The user cancels the portal dialog: `PermissionError`, a message in the window, no hang, no session left open (Task 2, Task 6).
2. The user presses "Stop sharing" in GNOME's top bar mid-recording: the recorder ends and the window reports the problem instead of hanging (Task 4, Task 5, Task 6).
3. `gst-launch-1.0` or the `pipewiresrc` plugin is missing: a message that names the package to install (Task 5).
4. Odd or non-1920 stream sizes and fractional scaling: frames keep the stream size, and the dragged area maps to the right pixels (Task 5, Task 7).
5. Leftover `gst-launch-1.0` processes or an open portal session after Stop, Escape, or closing the app (Task 4, Task 6, Task 8).

---

### Task 1: Spike on the real portal

**Files:**
- Create: `tools/portal_spike.py`
- Create: `docs/superpowers/wayland-spike.md`
- Modify: `docs/superpowers/baseline.md` (append a "Wayland portal" section)

**Interfaces:**
- Consumes: nothing.
- Produces: the findings in `wayland-spike.md` that Tasks 2-5 rely on: the real shape of the `Start` results, whether `fd=`/`path=` work with `pipewiresrc`, the delivered frame size and rate, CPU use, and whether any cursor position is reachable from `gst-launch-1.0` (expected: no).

This task needs the user at the machine to click the portal dialog. Ask them to run it with `! uv run --with jeepney python tools/portal_spike.py`.

- [ ] **Step 1: Write `tools/portal_spike.py`**

A standalone script (module docstring included) that: opens a session bus connection with `jeepney.io.blocking` and `enable_fds=True`; calls `CreateSession`, `SelectSources` (`types=1`, `cursor_mode=2`), `Start`, waiting for each `Response` signal (subscribe with `AddMatch` before calling); calls `OpenPipeWireRemote` and keeps the fd; prints the `Start` results verbatim. Then runs `gst-launch-1.0 -q pipewiresrc fd=<fd> path=<node> always-copy=true ! videoconvert ! videoscale ! video/x-raw,format=BGRA,width=<W>,height=<H> ! fdsink fd=1 sync=false` with `pass_fds=(fd,)` for 10 s, counts the bytes read from stdout, and prints: frames received (bytes / (W*H*4)), frames per second, and the child's CPU seconds (`resource.getrusage(RUSAGE_CHILDREN)`). Finally closes the session with `Session.Close`. Repeat the stream part once more with `cursor_mode=4` and `GST_DEBUG=pipewire:5` on stderr, and print any line containing "cursor".

- [ ] **Step 2: Run it on the dev machine**

Run: `uv run --with jeepney python tools/portal_spike.py` (the user clicks the share dialog).
Expected: prints stream `size`/`position`, about 10 s of frames, and the cursor lines (or none).

- [ ] **Step 3: Record the findings**

Write `docs/superpowers/wayland-spike.md` with: the exact `Start` results, the real frame rate and CPU for 10 s, whether the delivered frame size equals the portal `size` (HiDPI check), and the verdict on cursor metadata. Append the same numbers to `docs/superpowers/baseline.md`. If the spike finds a way to read the cursor position without `PyGObject`, add a ledger `Ruling:` and write it into the findings; do not implement it in this plan. If `pipewiresrc fd=`/`path=` does not work, stop and ask: the plan's architecture depends on it.

- [ ] **Step 4: Commit**

```bash
git add tools/portal_spike.py docs/superpowers/wayland-spike.md docs/superpowers/baseline.md
git commit -m "docs(wayland): record the portal spike on GNOME"
```

---

### Task 2: ScreenCast client over a transport

**Files:**
- Create: `src/anypoach/capture/portal.py`
- Create: `tests/test_portal_client.py`
- Modify: `pyproject.toml` (extra `ui` gains `"jeepney>=0.9; sys_platform == 'linux'"`)

**Interfaces:**
- Consumes: findings of Task 1 (shape of `Start` results).
- Produces, all in `anypoach.capture.portal`:
  - `PortalStream(node_id: int, position: tuple[int, int], size: tuple[int, int])` frozen dataclass.
  - `PortalTransport` Protocol: `request(method: str, *args, options: dict[str, Any]) -> tuple[int, dict[str, Any]]` (sends the call, waits for the matching `Response`, returns `(code, results)`); `open_remote(session_handle: str) -> int` (a file descriptor); `close_session(session_handle: str) -> None`; `close() -> None`.
  - `ScreenCastSession` dataclass: `handle: str`, `streams: list[PortalStream]`, `pipewire_fd: int`.
  - `ScreenCastClient(transport: PortalTransport)` with `start(*, cursor_mode: int = 2) -> ScreenCastSession` and `close(session: ScreenCastSession) -> None`.

- [ ] **Step 1: Write the failing tests** (`tests/test_portal_client.py`, with a `FakeTransport` that pops `(code, results)` from a list, records `(method, args, options)`, and returns fd 42 from `open_remote`)

```python
SESSION = (0, {"session_handle": "/s/1"})
STREAMS = (0, {"streams": [(57, {"position": (0, 0), "size": (1920, 1080), "source_type": 1})]})

def test_start_returns_the_stream_and_the_pipewire_fd():
    t = FakeTransport([SESSION, (0, {}), STREAMS])
    session = ScreenCastClient(t).start()
    assert session.streams == [PortalStream(57, (0, 0), (1920, 1080))]
    assert (session.handle, session.pipewire_fd) == ("/s/1", 42)
    assert [c[0] for c in t.calls] == ["CreateSession", "SelectSources", "Start", "OpenPipeWireRemote"]

def test_sources_ask_for_a_monitor_with_the_cursor_embedded_and_no_stored_permission():
    t = FakeTransport([SESSION, (0, {}), STREAMS]); ScreenCastClient(t).start()
    options = t.calls[1][2]
    assert (options["types"], options["cursor_mode"]) == (1, 2)
    assert "persist_mode" not in options and "restore_token" not in options

def test_cancelling_the_dialog_raises_permission_error_and_closes_the_session():
    t = FakeTransport([SESSION, (0, {}), (1, {})])
    with pytest.raises(PermissionError):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]

def test_a_portal_failure_raises_oserror_and_closes_the_session():
    t = FakeTransport([SESSION, (2, {})])
    with pytest.raises(OSError):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]

def test_a_start_without_streams_raises_oserror():
    t = FakeTransport([SESSION, (0, {}), (0, {"streams": []})])
    with pytest.raises(OSError, match="no screen"):
        ScreenCastClient(t).start()
    assert t.closed == ["/s/1"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_portal_client.py -q`
Expected: FAIL with `ModuleNotFoundError: anypoach.capture.portal`.

- [ ] **Step 3: Implement the module**

Create `portal.py` with the types above. `start` runs `CreateSession` (options `handle_token`, `session_handle_token`), `SelectSources` (`types=1`, `cursor_mode`, `multiple=False`), `Start` (parent window `""`), then `open_remote`; unique tokens come from `uuid`. Map response code 1 to `PermissionError("Screen sharing was cancelled.")`, any other nonzero code to `OSError`. On any failure after the session exists, call `transport.close_session` before raising. Add `jeepney` to the `ui` extra and run `uv lock`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_portal_client.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/portal.py tests/test_portal_client.py pyproject.toml uv.lock
git commit -m "feat(capture): add the ScreenCast portal client"
```

---

### Task 3: Jeepney transport against a private bus

**Files:**
- Modify: `src/anypoach/capture/portal.py` (add `JeepneyTransport`)
- Create: `tests/portal_fake.py` (a fake portal service), `tests/test_portal_transport.py`

**Interfaces:**
- Consumes: `PortalTransport`, `ScreenCastClient` from Task 2.
- Produces: `JeepneyTransport()` in `anypoach.capture.portal`, implementing `PortalTransport` on the session bus named by `DBUS_SESSION_BUS_ADDRESS`; its constructor raises `OSError` when there is no session bus.

`tests/portal_fake.py` starts `dbus-daemon --session --print-address --nofork` as a subprocess, runs a thread that owns `org.freedesktop.portal.Desktop`, answers `CreateSession`/`SelectSources`/`Start` with a request object path and immediately emits the matching `Response` signal, and answers `OpenPipeWireRemote` with an fd of `/dev/null`. The tests skip when `dbus-daemon` is not on `PATH`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_full_start_through_the_real_transport(fake_portal):
    client = ScreenCastClient(JeepneyTransport())
    session = client.start()
    assert session.streams[0].size == (640, 480)
    assert os.fstat(session.pipewire_fd)  # a live fd arrived over DBus
    client.close(session)
    assert fake_portal.closed_sessions == [session.handle]

def test_a_response_sent_before_the_reply_is_read_is_not_lost(fake_portal):
    fake_portal.emit_before_reply = True
    assert ScreenCastClient(JeepneyTransport()).start().streams

def test_cancelling_in_the_portal_becomes_permission_error(fake_portal):
    fake_portal.start_code = 1
    with pytest.raises(PermissionError):
        ScreenCastClient(JeepneyTransport()).start()

def test_no_session_bus_is_an_oserror(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/nonexistent")
    with pytest.raises(OSError):
        JeepneyTransport()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_portal_transport.py -q`
Expected: FAIL with `ImportError: cannot import name 'JeepneyTransport'`.

- [ ] **Step 3: Implement `JeepneyTransport`**

Use `jeepney.io.blocking.open_dbus_connection(bus="SESSION", enable_fds=True)`. For `request`: compute the request path `/org/freedesktop/portal/desktop/request/<sender>/<token>` (sender is the unique name without `:`, dots as underscores, token from `options["handle_token"]`), add the `Response` match rule and subscribe *before* sending the call, then read messages until that signal arrives. Method signatures by name: `CreateSession` `a{sv}`; `SelectSources` `oa{sv}`; `Start` `osa{sv}`. `open_remote` calls `OpenPipeWireRemote(o, a{sv})` and returns the fd from the reply. `close_session` calls `org.freedesktop.portal.Session.Close` on the session path. Import `jeepney` inside the constructor.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_portal_transport.py -q`
Expected: 4 passed (or skipped with the reason `dbus-daemon not found`).

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/portal.py tests/portal_fake.py tests/test_portal_transport.py
git commit -m "feat(capture): talk to the portal over DBus with jeepney"
```

---

### Task 4: The PipeWire frame reader

**Files:**
- Create: `src/anypoach/capture/pipewire.py`
- Create: `tests/test_pipewire_stream.py`

**Interfaces:**
- Consumes: `Frame` from `anypoach.capture.backend`.
- Produces, in `anypoach.capture.pipewire`:
  - `gst_command(fd: int, node_id: int, size: tuple[int, int]) -> list[str]`.
  - `PipeWireStream(command: Sequence[str], size: tuple[int, int], *, pass_fds: Sequence[int] = (), clock: Callable[[], float] = time.perf_counter)` with `start() -> None`, `wait_first_frame(timeout_s: float = 5.0) -> Frame` (raises `OSError` on timeout or if the process exits first), `latest() -> Frame` (raises `OSError("The screen sharing stopped.")` once the stream ended), `ended: bool` property, `close() -> None` (kills the process, joins the reader, safe to call twice).

- [ ] **Step 1: Write the failing tests** (a helper builds a command `[sys.executable, "-c", script]` that writes frames of constant value `n` for `n in range(count)` with a pause between them, so no GStreamer is needed)

```python
def test_gst_command_pins_the_pipeline():
    assert gst_command(7, 57, (1920, 1080)) == [
        "gst-launch-1.0", "-q", "pipewiresrc", "fd=7", "path=57", "always-copy=true", "!",
        "videoconvert", "!", "videoscale", "!", "video/x-raw,format=BGRA,width=1920,height=1080", "!",
        "fdsink", "fd=1", "sync=false"]

def test_latest_returns_the_newest_complete_frame():
    stream = PipeWireStream(producer(frames=5, pause=0.05), (4, 2)); stream.start()
    try:
        assert stream.wait_first_frame().pixels.shape == (2, 4, 4)
        time.sleep(0.4)
        assert stream.latest().pixels[0, 0, 0] == 4
    finally:
        stream.close()

def test_a_half_written_frame_is_never_returned():
    stream = PipeWireStream(producer(frames=1, partial=True), (4, 2)); stream.start()
    with pytest.raises(OSError):
        stream.wait_first_frame(timeout_s=1)
    stream.close()

def test_the_first_frame_wait_times_out():
    stream = PipeWireStream(producer(frames=0, sleep_forever=True), (4, 2)); stream.start()
    with pytest.raises(OSError, match="timed out"):
        stream.wait_first_frame(timeout_s=0.3)
    stream.close()

def test_latest_after_the_process_ended_raises():
    stream = PipeWireStream(producer(frames=1), (4, 2)); stream.start()
    stream.wait_first_frame(); time.sleep(0.3)
    assert stream.ended
    with pytest.raises(OSError, match="stopped"):
        stream.latest()
    stream.close()

def test_close_kills_the_process():
    stream = PipeWireStream(producer(frames=0, sleep_forever=True), (4, 2)); stream.start()
    process = stream._process
    stream.close(); stream.close()
    assert process.poll() is not None

@pytest.mark.skipif(shutil.which("gst-launch-1.0") is None, reason="GStreamer not installed")
def test_a_real_gstreamer_pipeline_delivers_bgra_frames():
    command = ["gst-launch-1.0", "-q", "videotestsrc", "num-buffers=10", "!", "videoconvert", "!", "videoscale", "!",
               "video/x-raw,format=BGRA,width=64,height=48", "!", "fdsink", "fd=1", "sync=false"]
    stream = PipeWireStream(command, (64, 48)); stream.start()
    try:
        assert stream.wait_first_frame().pixels.shape == (48, 64, 4)
    finally:
        stream.close()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_pipewire_stream.py -q`
Expected: FAIL with `ModuleNotFoundError: anypoach.capture.pipewire`.

- [ ] **Step 3: Implement the module**

`start` launches `subprocess.Popen(command, stdout=PIPE, stderr=DEVNULL, pass_fds=pass_fds)` and a daemon reader thread that reads exactly `width*height*4` bytes per frame (`readinto` a bytearray, loop until full), builds a `Frame(np.frombuffer(...).reshape(h, w, 4).copy(), clock())` under a lock, and sets an event on the first frame; a short read means the stream ended. `close` terminates, waits 1 s, then kills.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_pipewire_stream.py -q`
Expected: 7 passed (the GStreamer test is skipped if not installed).

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/pipewire.py tests/test_pipewire_stream.py
git commit -m "feat(capture): read PipeWire frames through a gst-launch subprocess"
```

---

### Task 5: PortalBackend

**Files:**
- Create: `src/anypoach/capture/portal_backend.py`
- Create: `tests/test_portal_backend.py`

**Interfaces:**
- Consumes: `ScreenCastClient`, `ScreenCastSession`, `PortalStream` (Task 2), `JeepneyTransport` (Task 3), `PipeWireStream`, `gst_command` (Task 4), `Frame`, `Screen` from `backend.py`.
- Produces, in `anypoach.capture.portal_backend`:
  - `portal_problems(which: Callable[[str], str | None] = shutil.which, run: Callable = subprocess.run) -> list[str]`: human messages, empty when GStreamer, the `pipewiresrc` plugin, and a DBus session bus are all present.
  - `PortalBackend(*, client_factory=..., stream_factory=...)` implementing `CaptureBackend` plus `preview() -> Frame` (opens the session, so the portal asks for consent, and returns the first frame), `active: bool`, `close() -> None`. `screens()` is `[]` until `preview()` has run, then one `Screen(1, Rect(0, 0, W, H), 1.0)` in stream pixels. `grab(region)` crops the newest frame; the region is in stream pixels with origin at the top left.

- [ ] **Step 1: Write the failing tests** (fakes for the client factory and the stream factory; frames are 100x80 with `pixels[y, x] = (x, y, 0, 255)`)

```python
def test_screens_are_empty_until_the_preview_opens_the_session():
    assert PortalBackend(**fakes()).screens() == []

def test_preview_opens_the_session_and_returns_the_first_frame():
    backend = PortalBackend(**fakes())
    assert backend.preview().pixels.shape == (80, 100, 4) and backend.active
    assert backend.screens() == [Screen(1, Rect(0, 0, 100, 80), 1.0)]

def test_grab_crops_the_newest_frame():
    backend = started(); frame = backend.grab(Rect(10, 20, 30, 40))
    assert frame.pixels.shape == (40, 30, 4) and tuple(frame.pixels[0, 0, :2]) == (10, 20)

def test_grab_clamps_a_region_that_overflows_the_frame():
    assert started().grab(Rect(90, 70, 50, 50)).pixels.shape == (10, 10, 4)

def test_grab_outside_the_frame_raises():
    with pytest.raises(OSError, match="outside"):
        started().grab(Rect(500, 500, 10, 10))

def test_grab_after_the_stream_ended_raises_oserror():
    backend = started(); backend.stream.end()
    with pytest.raises(OSError, match="stopped"):
        backend.grab(Rect(0, 0, 10, 10))

def test_grab_before_preview_raises_permission_error():
    with pytest.raises(PermissionError):
        PortalBackend(**fakes()).grab(Rect(0, 0, 10, 10))

def test_a_cancelled_dialog_leaves_the_backend_inactive():
    backend = PortalBackend(**fakes(cancel=True))
    with pytest.raises(PermissionError):
        backend.preview()
    assert not backend.active

def test_close_stops_the_stream_and_the_session_once():
    backend = started(); backend.close(); backend.close()
    assert backend.stream.closed == 1 and backend.client.closed == 1 and not backend.active

def test_problems_name_the_missing_package():
    which = lambda name: None
    assert any("gstreamer1.0-tools" in p for p in portal_problems(which=which))

def test_problems_name_the_missing_pipewire_plugin():
    run = lambda *a, **k: types.SimpleNamespace(returncode=1)
    assert any("gstreamer1.0-pipewire" in p for p in portal_problems(which=lambda n: "/bin/" + n, run=run))

def test_no_problems_when_everything_is_present(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/x")
    run = lambda *a, **k: types.SimpleNamespace(returncode=0)
    assert portal_problems(which=lambda n: "/bin/" + n, run=run) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_portal_backend.py -q`
Expected: FAIL with `ModuleNotFoundError: anypoach.capture.portal_backend`.

- [ ] **Step 3: Implement the module**

`preview()` first calls `portal_problems()` and raises `OSError` with the joined messages if any; then `client.start()` → `PipeWireStream(gst_command(fd, node, size), size, pass_fds=(fd,))` → `start()` → `wait_first_frame()`. If `wait_first_frame` fails, close the session and stream before re-raising. `grab` clamps the region to the frame, rounds to whole pixels, and raises `OSError("Region is outside the shared screen")` when nothing is left.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_portal_backend.py -q`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/portal_backend.py tests/test_portal_backend.py
git commit -m "feat(capture): add the Wayland portal capture backend"
```

---

### Task 6: Backend selection and the controller's preview flow

**Files:**
- Create: `src/anypoach/capture/default.py`
- Modify: `src/anypoach/ui/controller.py`
- Create: `tests/test_default_backend.py`
- Modify: `tests/test_ui_controller.py`

**Interfaces:**
- Consumes: `PortalBackend` (Task 5), `MssBackend`.
- Produces:
  - `default_backend(environ: Mapping[str, str] = os.environ, platform: str = sys.platform) -> CaptureBackend` in `anypoach.capture.default`: `PortalBackend` when `platform` starts with `linux` and `environ.get("XDG_SESSION_TYPE") == "wayland"`, otherwise `MssBackend`.
  - On `Controller`: a public read-only `backend` property (the tests inspect the fake through it), `supports_preview: bool` (the backend has `preview`), `preview() -> Frame | None` (returns the first frame; on `PermissionError` or `OSError` sets `message` and returns `None`), `close() -> None` (closes the backend when it has `close`). `stop()` and a cancelled selection reset `_region` to `None` and close a preview backend, so the next recording asks for consent again.

- [ ] **Step 1: Write the failing tests**

```python
def test_wayland_gets_the_portal_backend():
    assert isinstance(default_backend({"XDG_SESSION_TYPE": "wayland"}, "linux"), PortalBackend)

def test_x11_and_windows_keep_mss():
    assert isinstance(default_backend({"XDG_SESSION_TYPE": "x11"}, "linux"), MssBackend)
    assert isinstance(default_backend({}, "win32"), MssBackend)

def test_controller_without_a_preview_backend_does_not_support_it(controller):
    assert not controller.supports_preview and controller.preview() is None

def test_a_cancelled_portal_dialog_becomes_a_message(preview_controller):
    preview_controller.backend.fail_with(PermissionError("Screen sharing was cancelled."))
    assert preview_controller.preview() is None and "cancelled" in preview_controller.message

def test_stop_closes_the_portal_and_forgets_the_region(preview_controller):
    preview_controller.preview(); preview_controller.choose_region(Rect(0, 0, 50, 50))
    preview_controller.start(); preview_controller.stop()
    assert preview_controller.backend.closed == 1
    preview_controller.start()
    assert "Choose an area" in preview_controller.message

def test_a_stream_that_ended_before_recording_is_a_message(preview_controller):
    preview_controller.preview(); preview_controller.choose_region(Rect(0, 0, 50, 50))
    preview_controller.backend.end_stream()
    preview_controller.start()
    assert preview_controller.state == "idle" and "stopped" in preview_controller.message

def test_close_releases_the_backend(preview_controller):
    preview_controller.preview(); preview_controller.close()
    assert preview_controller.backend.closed == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_default_backend.py tests/test_ui_controller.py -q`
Expected: FAIL (`default` module and controller attributes missing).

- [ ] **Step 3: Implement**

Write `default.py` with a lazy import of `PortalBackend`. In `Controller`, add the three members, and in `stop()` close a preview backend in a `finally` after the recorder stops (the recorder needs the backend until then). Keep the existing messages intact.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q && uv run ruff check src tests tools`
Expected: all passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/default.py src/anypoach/ui/controller.py tests/test_default_backend.py tests/test_ui_controller.py
git commit -m "feat(ui): choose the portal backend on Wayland and preview before recording"
```

---

### Task 7: Frozen-frame area selection

**Files:**
- Create: `src/anypoach/ui/frozen_selection.py`
- Create: `tests/test_frozen_selection.py`

**Interfaces:**
- Consumes: `Frame` from `backend.py`, `Rect`.
- Produces, in `anypoach.ui.frozen_selection`:
  - `frame_rect(start, end, *, widget_size: tuple[float, float], frame_size: tuple[int, int]) -> Rect`: the dragged corners (widget coordinates) as a rectangle in frame pixels, sorted, clamped to the frame.
  - `FrozenSelection(frame: Frame)` (a `QWidget`): paints the frame stretched to the widget with the same dimmed cut-out as `SelectionOverlay`; signals `selected(Rect)` (frame pixels) and `cancelled()`; Escape cancels.

- [ ] **Step 1: Write the failing tests**

```python
def test_frame_rect_scales_widget_pixels_to_frame_pixels():
    assert frame_rect((10, 10), (60, 30), widget_size=(100, 50), frame_size=(200, 100)) == Rect(20, 20, 100, 40)

def test_frame_rect_accepts_a_drag_in_any_direction():
    assert frame_rect((60, 30), (10, 10), widget_size=(100, 50), frame_size=(100, 50)) == Rect(10, 10, 50, 20)

def test_frame_rect_clamps_to_the_frame():
    assert frame_rect((-20, -5), (500, 500), widget_size=(100, 50), frame_size=(100, 50)) == Rect(0, 0, 100, 50)

def test_a_drag_emits_the_area_in_frame_pixels():
    widget = FrozenSelection(frame(200, 100)); widget.resize(100, 50)
    got = []; widget.selected.connect(got.append)
    QTest.mousePress(widget, Qt.LeftButton, pos=QPoint(10, 10))
    QTest.mouseMove(widget, QPoint(60, 30))
    QTest.mouseRelease(widget, Qt.LeftButton, pos=QPoint(60, 30))
    assert got == [Rect(20, 20, 100, 40)]

def test_escape_cancels():
    widget = FrozenSelection(frame(20, 10)); seen = []
    widget.cancelled.connect(lambda: seen.append(1))
    QTest.keyClick(widget, Qt.Key_Escape)
    assert seen == [1]

def test_the_widget_has_an_accessible_name():
    assert "Drag" in FrozenSelection(frame(20, 10)).accessibleName()
```

(`QT_QPA_PLATFORM=offscreen`; follow the fixtures of `tests/test_ui_window.py`.)

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_frozen_selection.py -q`
Expected: FAIL with `ModuleNotFoundError: anypoach.ui.frozen_selection`.

- [ ] **Step 3: Implement the module**

Convert the BGRA array to a `QImage(Format_ARGB32)` copy (byte order matches on little endian). A release with a drag under 2 frame pixels emits nothing and keeps the widget open, as `Controller.choose_region` rejects tiny areas.

- [ ] **Step 4: Run to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_frozen_selection.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/frozen_selection.py tests/test_frozen_selection.py
git commit -m "feat(ui): select the capture area on a frozen frame"
```

---

### Task 8: Window wiring

**Files:**
- Modify: `src/anypoach/ui/app.py`
- Modify: `tests/test_ui_window.py`

**Interfaces:**
- Consumes: `default_backend` (Task 6), `Controller.supports_preview/preview/close` (Task 6), `FrozenSelection` (Task 7).
- Produces: `main()` builds the controller with `default_backend()`; `MainWindow._choose` uses `FrozenSelection` when `controller.supports_preview`, the existing `SelectionOverlay` otherwise; `_leave_the_screen` minimizes the window when no tray exists (GNOME has no tray by default) instead of leaving it in the video; closing the app and cancelling a frozen selection call `controller.close()`.

- [ ] **Step 1: Write the failing tests** (a fake preview controller whose `preview()` returns a 20x10 frame)

```python
def test_choosing_an_area_on_a_preview_backend_shows_the_frozen_selection(window_with_preview):
    window_with_preview._choose()
    assert isinstance(window_with_preview._overlay, FrozenSelection)

def test_a_failed_preview_shows_the_message_and_keeps_the_window(window_with_failing_preview):
    window_with_failing_preview._choose()
    assert window_with_failing_preview.isVisible() and "cancelled" in window_with_failing_preview.status.text()

def test_cancelling_the_frozen_selection_closes_the_portal_session(window_with_preview):
    window_with_preview._choose(); window_with_preview._overlay.cancelled.emit()
    assert window_with_preview.controller.backend.closed == 1 and window_with_preview.isVisible()

def test_without_a_tray_the_window_minimizes_while_recording(window_with_preview, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window_with_preview._leave_the_screen()
    assert window_with_preview.isMinimized()

def test_closing_the_window_releases_the_backend(window_with_preview):
    window_with_preview.close()
    assert window_with_preview.controller.backend.closed >= 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_window.py -q`
Expected: FAIL on the new tests only.

- [ ] **Step 3: Implement**

In `_choose`: if `supports_preview`, hide the window, call `controller.preview()`; on `None` show the window with the message; otherwise create `FrozenSelection`, connect `selected` to `_chosen` and `cancelled` to a handler that calls `controller.close()` and shows the window, then `showFullScreen()`. Override `closeEvent` to call `controller.close()` and accept. In `_leave_the_screen`, call `showMinimized()` when the tray is unavailable on non-Windows systems.

- [ ] **Step 4: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: all passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/app.py tests/test_ui_window.py
git commit -m "feat(ui): wire the Wayland preview into the window"
```

---

### Task 9: CI, documentation, and the real GNOME check

**Files:**
- Modify: `.github/workflows/python.yml` (Linux apt line gains `gstreamer1.0-tools gstreamer1.0-plugins-base dbus`)
- Modify: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: documented Wayland support and the verified manual checklist.

- [ ] **Step 1: Update CI and docs**

- `python.yml`: add the packages above so the GStreamer and DBus tests run on Linux.
- `README.md`: in "Status and limitations" replace the Wayland note with the real state: supported through the portal, GNOME tested, others best effort, no pointer trace (cursor is drawn into the video by the compositor), needs `gstreamer1.0-tools`, `gstreamer1.0-plugins-base`, and `gstreamer1.0-pipewire`; add them to Quick Start for Linux. Add one affectionate line to the roast: the original needed a Mac, a menu bar, and macOS 15, and never asked a Wayland user how they were doing.
- `CONTRIBUTING.md` "Manual checks": add the Wayland checklist of Step 3.
- `CLAUDE.md`: update the architecture bullet 2 and the Gotchas line about Wayland.

- [ ] **Step 2: Run the whole suite and lint**

Run: `uv run pytest -q && QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_window.py -q && uv run ruff check src tests tools`
Expected: all passed, ruff clean.

- [ ] **Step 3: Verify on the real GNOME Wayland session (the user runs it)**

Ask the user to run `! uv run anypoach` and report each result:
1. Choose area: the portal dialog appears, the frozen frame fills the screen, drag selects, Escape cancels and the GNOME sharing indicator disappears.
2. Record 10 s of a moving area, stop: keyframes and palette appear, and the indicator disappears.
3. Copy the prompt, then read it through an MCP client with `anypoach_read_brief` and `anypoach_read_moment`.
4. Press "Stop sharing" in GNOME's top bar mid-recording: the window reports it instead of hanging.
5. Decline the portal dialog: the window shows the cancelled message.
6. `pgrep gst-launch` shows nothing after stop and after closing the app.
Also record CPU use while recording in `docs/superpowers/baseline.md`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/python.yml README.md CONTRIBUTING.md CLAUDE.md docs/superpowers/baseline.md
git commit -m "docs(wayland): document portal capture and its manual checks"
```
