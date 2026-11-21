# AnyPoach v0.2.1: macOS Pointer and Screen-Recording Permission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recording on macOS trustworthy: a pointer trace and click ring on the video, regions that land on the right pixels on Retina, and a clear message instead of a silent wallpaper-only video when Screen Recording is not allowed.

**Architecture:** One thin `ctypes` wrapper over CoreGraphics (`anypoach/macos.py`) answers three questions: where are the displays and what is each one's scale, where is the pointer and which buttons are down, and is Screen Recording allowed. `MacPointerSource` and a scale-aware `MssBackend.grab` both use it, so the pointer and the video share one pixel space. The wrapper takes an injectable library handle, so every rule is tested on Linux with a fake; CI on `macos-latest` runs a smoke test of the real calls; a human-run spike confirms the assumptions the fakes encode.

**Tech Stack:** Python 3.11+, `ctypes` (no new dependency, no `pyobjc`), `mss` (already used), PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-anypoach-fidelity-design.md` (v0.2 line: "no macOS, ponteiro por `CGEventSource` e aviso de permissão de gravação de tela"); roadmap row v0.2.1 in `docs/superpowers/poach-parity.md`. The original does the same with `CGEventSource.buttonState` and `NSEvent.mouseLocation` (`apps/macos/Sources/Capture/PointerTrace.swift`), polling only.

## Global Constraints

- macOS 12 or newer. No new dependency: CoreGraphics is reached through `ctypes` (`ctypes.util.find_library("ApplicationServices")`).
- Only pointer position and button state are read, by polling. No event taps, no global hooks, no keyboard capture, no Input Monitoring or Accessibility permission requested.
- Pointer coordinates and capture regions share one space: global physical pixels, top-left origin, `Screen.bounds` and `Rect` as everywhere else. CoreGraphics speaks points, so conversion happens in exactly two places: `MacPointerSource.sample` and `MssBackend.grab`.
- Scale is `pixel width / point width` of a display, never assumed to be 2.0 and never written into a brief when unknown (`deviceScale` stays `null` then).
- No `print` to stdout anywhere near `anypoach.mcp`; the new modules do not import it anyway.
- Commits: Conventional Commits with a scope, atomic, staged by file name, no AI attribution lines. Implementation and docs go in separate commits.
- Docstrings in Google style, line length 110. Run the suite with `QT_QPA_PLATFORM=offscreen uv run pytest -q` and lint with `uv run ruff check src tests tools`.
- README and CONTRIBUTING are updated in the docs task (commands, permissions and platform status change).
- Linux is the only local platform. Anything that needs a real Mac is a manual check in Task 1 or Task 7 and is reported as not run until a person runs it.

## Review Focus

- A Retina display (scale 2.0) next to a 1x display: a region chosen on either must yield a frame whose size equals the region in physical pixels. Pinned in Task 4.
- The pointer on a second display with a negative origin and a different scale: the sample must be converted with that display's scale, not the first one's. Pinned in Task 3.
- Screen Recording denied: `mss` does not fail, it returns an image without other apps' windows. Recording must be refused with the System Settings path in the message, before the window hides. Pinned in Task 5.
- CoreGraphics or the permission symbol missing (older macOS, odd sandbox): the trace degrades to `available: false` and the permission gate steps aside; nothing raises into the window. Pinned in Tasks 2 and 3.
- A display added or removed mid-session, or a pointer reported outside every known display: refresh the display list once, then clamp to the nearest display instead of raising. Pinned in Task 3.

---

## File Structure

- Create `src/anypoach/macos.py`: the CoreGraphics wrapper and its two value types. One responsibility: talk to the OS, return plain Python.
- Create `src/anypoach/pointer/macos.py`: `MacPointerSource`, a `PointerSource` that converts points to physical pixels.
- Modify `src/anypoach/pointer/__init__.py`: `default_source()` returns it on `darwin`.
- Modify `src/anypoach/capture/mss_backend.py`: scale-aware `screens()` and `grab()` on `darwin` only.
- Modify `src/anypoach/ui/controller.py` and `src/anypoach/ui/app.py`: permission gate, tray icon fallback.
- Create `tools/macos_spike.py` and `docs/superpowers/macos-spike.md`: the measurements.
- Tests: `tests/test_macos_cg.py`, `tests/test_pointer_macos.py`, additions to `tests/test_capture_recorder.py`, `tests/test_ui_controller.py`, `tests/test_ui_window.py`, `tests/test_default_backend.py`.

---

### Task 1: Spike on a real Mac

The assumptions every later task encodes. This task needs a person with a Mac; the rest of the plan can be written and merged against fakes meanwhile, but the release waits for it.

**Files:**
- Create: `tools/macos_spike.py`
- Create: `docs/superpowers/macos-spike.md`

**Interfaces:**
- Produces: the facts A1 to A5 below, recorded as measured values. Later tasks' fakes copy these shapes.

Assumptions to confirm or correct:
- A1: `mss` reports monitors in points, and `grab` of a box in points returns an image in pixels (width = box width x scale).
- A2: `CGEventGetLocation(CGEventCreate(NULL))` returns points, global, top-left origin (primary display at 0,0; a display left of it has a negative x).
- A3: `CGEventSourceButtonState(0, button)` with button 0 left, 1 right, 2 center reflects the physical state with no permission prompt.
- A4: `CGDisplayBounds` (points) and `CGDisplayModeGetPixelWidth(CGDisplayCopyDisplayMode(id))` (real pixels; `CGDisplayPixelsWide` reports points on HiDPI modes, so it is not used) give the scale per display; `CGGetActiveDisplayList` lists them.
- A5: with Screen Recording denied, `mss.grab` returns a frame without error, and `CGPreflightScreenCaptureAccess()` returns false.

- [ ] **Step 1: Write `tools/macos_spike.py`**

It takes no arguments and prints, as plain lines: each display (id, bounds in points, pixel width and height, derived scale); `mss` monitors; for a 100x100-point box at the primary display's origin, the shape of the `mss` frame; `CGPreflightScreenCaptureAccess()`; then 5 seconds of pointer samples at 10 Hz (location, buttons) asking the person to move across displays and click left and right. Use `ctypes` only for CoreGraphics so the script doubles as a prototype for Task 2.

- [ ] **Step 2: Run it on a Mac with a Retina display, and again with a second display if available**

Run: `uv run python tools/macos_spike.py`
Expected: lines for each of A1 to A5; no traceback.

- [ ] **Step 3: Run it once with Screen Recording denied for the terminal** (System Settings, Privacy & Security, Screen Recording)

Expected: A5 confirmed: `mss` frame returned, preflight `False`.

- [ ] **Step 4: Write `docs/superpowers/macos-spike.md`** with the macOS version, hardware, the printed output, and one line per assumption: confirmed, or what was found. If an assumption was wrong, fix the matching constant in Tasks 2 to 5 before implementing them.

- [ ] **Step 5: Commit**

```bash
git add tools/macos_spike.py docs/superpowers/macos-spike.md
git commit -m "docs(macos): measure display scale, pointer space and the permission check"
```

---

### Task 2: CoreGraphics wrapper

**Files:**
- Create: `src/anypoach/macos.py`
- Test: `tests/test_macos_cg.py`

**Interfaces:**
- Produces:
  - `class Display(NamedTuple)`: `id: int`, `bounds: Rect` (points, top-left origin), `scale: float`.
  - `class CoreGraphics`: `__init__(self, lib: Any = None, cf: Any = None)` (loads `ApplicationServices` and `CoreFoundation` when `lib` and `cf` are None; raises `OSError` when it cannot; `cf` holds `CFRelease`), `displays(self) -> list[Display]`, `pointer(self) -> tuple[float, float]` (points), `button_down(self, button: Button) -> bool`, `screen_recording_allowed(self) -> bool | None` (None when the symbol is missing), `request_screen_recording(self) -> bool | None`.
  - `Button` and `Rect` are the existing types from `anypoach.pointer.trace`.

- [ ] **Step 1: Write the failing tests in `tests/test_macos_cg.py`** with a `FakeLib` whose attributes are small function objects accepting `.restype` and `.argtypes` assignment. Tests: `test_displays_scale_is_pixels_over_points` (one display 1512x982 points, 3024x1964 pixels gives `scale == 2.0`; another 1920x1080 for 1920x1080 gives `1.0`), `test_displays_keep_a_negative_origin`, `test_button_down_maps_left_right_other_to_0_1_2`, `test_pointer_returns_points`, `test_screen_recording_allowed_is_none_when_the_symbol_is_missing`, `test_a_missing_library_is_an_oserror` (patch `ctypes.util.find_library` to return None).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_macos_cg.py -v`
Expected: FAIL with `ModuleNotFoundError: anypoach.macos`.

- [ ] **Step 3: Implement the interfaces above in `src/anypoach/macos.py`**

Declare the C types once (`CGPoint`, `CGSize`, `CGRect` as `ctypes.Structure`, `CGFloat` as `c_double`) and set `restype`/`argtypes` for `CGEventCreate`, `CGEventGetLocation`, `CFRelease`, `CGEventSourceButtonState`, `CGGetActiveDisplayList`, `CGDisplayBounds`, `CGDisplayCopyDisplayMode`, `CGDisplayModeGetPixelWidth`, `CGDisplayModeRelease`, `CGPreflightScreenCaptureAccess`, `CGRequestScreenCaptureAccess`. `pointer()` must `CFRelease` the event it creates. Symbols that may not exist on every macOS (`CGPreflightScreenCaptureAccess`, `CGRequestScreenCaptureAccess`) are looked up with `getattr` and give None when absent.

- [ ] **Step 4: Add a darwin-only smoke test** `test_real_displays_have_a_positive_scale` marked `skipif(sys.platform != "darwin")`: `CoreGraphics().displays()` is non-empty and every scale is at least 1.0. It runs on the `macos-latest` job.

- [ ] **Step 5: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_macos_cg.py -v && uv run ruff check src tests tools`
Expected: PASS (smoke test skipped on Linux).

- [ ] **Step 6: Commit**

```bash
git add src/anypoach/macos.py tests/test_macos_cg.py
git commit -m "feat(macos): read displays, pointer and the recording permission through CoreGraphics"
```

---

### Task 3: macOS pointer source

**Files:**
- Create: `src/anypoach/pointer/macos.py`
- Modify: `src/anypoach/pointer/__init__.py`
- Test: `tests/test_pointer_macos.py`

**Interfaces:**
- Consumes: `CoreGraphics`, `Display` from Task 2.
- Produces: `class MacPointerSource` with `__init__(self, cg: CoreGraphics | None = None)` and `sample(self) -> PointerSample` (physical pixels, top-left origin, buttons `left`, `right`, `other`). `default_source()` returns one on `sys.platform == "darwin"`, and None when `CoreGraphics()` raises `OSError`.

- [ ] **Step 1: Write the failing tests** with a fake `CoreGraphics` (an object with `displays()`, `pointer()`, `button_down()`):
  - `test_points_become_pixels_with_the_scale_of_the_display_under_the_pointer`: displays `[Display(1, Rect(0, 0, 1512, 982), 2.0), Display(2, Rect(-1920, 0, 1920, 1080), 1.0)]`; pointer at `(100, 50)` gives `(200, 100)`; pointer at `(-1000, 40)` gives `(-1000, 40)`.
  - `test_origin_of_a_second_display_scales_from_the_global_origin`: a 2x display at `Rect(1512, 0, 1512, 982)`, pointer `(1612, 10)` gives `(3224, 20)` (global origin scaled, matching how `physical_rect` multiplies `origin * dpr`).
  - `test_buttons_report_left_right_and_other`.
  - `test_a_pointer_outside_every_display_refreshes_once_then_clamps`: first `displays()` returns one display, the pointer is outside it, a second `displays()` call returns two and the sample uses the matching one; if still outside, the nearest display's scale is used and nothing raises.
  - `test_default_source_is_none_when_coregraphics_is_missing` (monkeypatch `sys.platform` to `darwin` and make `CoreGraphics()` raise `OSError`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_pointer_macos.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `MacPointerSource`**

Read the display list in `__init__`; `sample()` finds the display whose bounds contain the point (points), multiplies both coordinates by its `scale`, and reads the three buttons. Keep a `ponytail:` comment: mixed-scale multi-display setups scale the global origin the same way `physical_rect` does, so their absolute pixel space is only exact when the chosen area and the pointer are on one display. Update `default_source()` and its docstring (macOS now has a source; Wayland is the only session without one).

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/pointer/macos.py src/anypoach/pointer/__init__.py tests/test_pointer_macos.py
git commit -m "feat(pointer): sample the pointer on macOS"
```

---

### Task 4: Regions in physical pixels on Retina

**Files:**
- Modify: `src/anypoach/capture/mss_backend.py`
- Test: `tests/test_capture_recorder.py` (next to `test_mss_backend_converts_regions_and_monitors`)

**Interfaces:**
- Consumes: `CoreGraphics.displays()` from Task 2.
- Produces: `MssBackend(..., cg: CoreGraphics | None = None)`. On `darwin`, `screens()` returns each display's bounds multiplied by its scale and `scale` set; `grab(region)` converts the physical `region` to points with the scale of the display that contains its top-left corner, grabs, and returns a `Frame` whose pixel size equals `round(region.width)` by `round(region.height)`. Other platforms behave exactly as today (`scale` 1.0, no conversion).

- [ ] **Step 1: Write the failing tests** with a fake `sct` modeled on Task 1's A1 (monitors in points, `grab` returns BGRA bytes of `box width x scale` by `box height x scale`):
  - `test_retina_region_is_converted_to_points_and_the_frame_has_the_region_size`: scale 2.0, region `Rect(200, 100, 800, 600)` makes the fake receive `{"left": 100, "top": 50, "width": 400, "height": 300}` and the frame shape is `(600, 800, 4)`.
  - `test_a_1x_display_next_to_a_retina_one_uses_its_own_scale`.
  - `test_other_platforms_do_not_convert` (platform injected as `linux`).
  - `test_screens_report_physical_bounds_and_scale_on_macos`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_capture_recorder.py -k "retina or 1x_display or convert or physical_bounds" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** with a `platform: str = sys.platform` constructor argument (like `default_backend`) so tests choose the branch. If the fake's frame size differs from the region size after conversion by rounding, crop or pad to the region size rather than passing a mismatched frame to the recorder.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/capture/mss_backend.py tests/test_capture_recorder.py
git commit -m "fix(capture): grab Retina regions in points and return physical pixels"
```

---

### Task 5: Screen-recording permission gate

**Files:**
- Modify: `src/anypoach/ui/controller.py`, `src/anypoach/ui/app.py`
- Test: `tests/test_ui_controller.py`

**Interfaces:**
- Consumes: `CoreGraphics.screen_recording_allowed()` and `request_screen_recording()`.
- Produces: `Controller(..., screen_access: Callable[[], bool | None] | None = None)` and `Controller.check_screen_access(self) -> bool`. It returns True when no checker is given or the checker returns True or None; otherwise it sets `message` to `"AnyPoach needs Screen Recording permission. Allow it in System Settings > Privacy & Security > Screen Recording, then quit and reopen AnyPoach."` and returns False. `Controller.start()` calls it first. The window calls `check_screen_access()` in `_record` before `_leave_the_screen()`, so a refusal never hides the window. On `darwin`, `app.py` passes a checker that calls `screen_recording_allowed()` and, when it is False, calls `request_screen_recording()` once per process so macOS shows its prompt.

- [ ] **Step 1: Write the failing tests:** `test_denied_screen_recording_is_a_message_and_nothing_starts` (checker returns False; `start()` leaves `state == "idle"` and `message` mentions `Screen Recording`), `test_an_unknown_permission_state_does_not_block` (checker returns None), `test_no_checker_does_not_block`, `test_the_prompt_is_requested_once` (the app-level checker, with a fake `CoreGraphics` counting `request_screen_recording` calls across two denied checks).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_ui_controller.py -k "screen_recording or permission or prompt" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the parameter, the method, the `start()` call, the `_record` call, and a small `macos_screen_access()` factory in `anypoach/macos.py` that builds the once-per-process checker; `app.py` uses it only when `sys.platform == "darwin"` and `CoreGraphics()` loads.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/macos.py src/anypoach/ui/controller.py src/anypoach/ui/app.py tests/test_ui_controller.py
git commit -m "feat(ui): refuse to record on macOS until Screen Recording is allowed"
```

---

### Task 6: A tray icon that exists on macOS

**Files:**
- Modify: `src/anypoach/ui/app.py`
- Test: `tests/test_ui_window.py`

**Interfaces:**
- Produces: `recording_icon() -> QIcon` in `app.py`: `QIcon.fromTheme("media-record")` when the theme has it, otherwise a drawn red dot. `_leave_the_screen` uses it. macOS has no icon theme, so today the menu-bar item would be blank and the only way to stop a recording invisible.

- [ ] **Step 1: Write the failing test** `test_recording_icon_is_never_null` with the theme lookup patched to return a null icon (offscreen Qt).

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_window.py -k recording_icon -v`
Expected: FAIL (`recording_icon` not defined).

- [ ] **Step 3: Implement `recording_icon()`** and use it where `QIcon.fromTheme("media-record")` is called.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/app.py tests/test_ui_window.py
git commit -m "fix(ui): draw the recording icon when the theme has none"
```

---

### Task 7: Docs, manual checks, version

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `docs/superpowers/poach-parity.md`, `pyproject.toml`, `src/anypoach/chrome_extension/manifest.json`, `src/anypoach/mcp/server.py`, `uv.lock`

- [ ] **Step 1: README.** In "Status and limitations" move macOS pointer sampling out of "Not done" and say what was run where (only what Task 1's spike and the manual checks below actually covered). In Quick Start add one line on the Screen Recording prompt and the restart it needs. Update the Highlights platform line and the `pointer` bullet under Key modules.

- [ ] **Step 2: CONTRIBUTING.** Add a macOS paragraph to "Manual checks": the first recording shows the system prompt or the refusal message with the System Settings path; after allowing and reopening, a 10 s recording has `pointerTrace.available == true`, a click ring where you clicked, and a frame size equal to the chosen area in physical pixels on a Retina display; the same on a second display if you have one; the menu-bar item is visible while recording and stops it. Mention `tools/macos_spike.py` next to `tools/portal_spike.py`. Update the "Data handling" paragraph: macOS polls position and buttons through CoreGraphics and asks for no input permission.

- [ ] **Step 3: AGENTS.md and CLAUDE.md.** In both, replace "macOS has no source" statements (the `pointer` bullet in CLAUDE.md's architecture item 2 and the Gotchas) with the new state.

- [ ] **Step 4: Roadmap.** In `poach-parity.md`: v0.2.0 published, v0.2.1 in progress; the Ponteiro row says macOS is covered; the Captura macOS caveat points to `macos-spike.md`.

- [ ] **Step 5: Run the manual checks of Step 2 on a Mac** and record the result in the PR description. Anything not run is listed as not run.

- [ ] **Step 6: Version bump** to `0.2.1` in `pyproject.toml`, `manifest.json` and `server.py` (a test keeps the first two equal), then `uv lock`.

- [ ] **Step 7: Run everything**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS; CI green on Ubuntu, Windows and macOS.

- [ ] **Step 8: Commit docs and version separately**

```bash
git add README.md CONTRIBUTING.md AGENTS.md CLAUDE.md docs/superpowers/poach-parity.md
git commit -m "docs(macos): document the pointer, the permission prompt and the manual checks"
git add pyproject.toml src/anypoach/chrome_extension/manifest.json src/anypoach/mcp/server.py uv.lock
git commit -m "chore(release): prepare v0.2.1"
```

Tag and release only after the maintainer says so.
