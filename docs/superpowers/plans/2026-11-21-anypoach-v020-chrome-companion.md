# AnyPoach v0.2a: Chrome Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person select a component in Chrome, record its interaction in AnyPoach, and give the assistant the page's real computed sizes, typography, events and animation timing next to the video.

**Architecture:** A small Manifest V3 extension (plain JavaScript, no build) records one chosen component and posts snapshots to a loopback HTTP server that lives inside the AnyPoach window process. The server pairs with a code, validates the evidence, keeps the latest session for 180 s, and the `Controller` attaches the session that overlaps the recording to the brief as `evidence.browserEvidence` (the key the MCP server already reads). The MCP server and the handoff prompt are taught to prefer those values over measurements taken from video.

**Tech Stack:** Python 3.11+ (`http.server`, `pydantic`, already a dependency through `mcp`), PySide6, JavaScript (MV3 service worker, content script), pytest, Node (test only, skipped when absent), headless Chrome (test only, skipped when absent), uv.

**Spec:** `docs/superpowers/specs/2026-11-21-anypoach-fidelity-design.md` (section "Design da extensão do Chrome"). The macOS items of v0.2 (`CGEventSource` pointer, screen-recording permission hint) get their own plan.

## Global Constraints

- The server binds `127.0.0.1` only, on port `47832`, and runs only while the AnyPoach window is open. Nothing listens otherwise.
- Every request needs `Authorization: Bearer <pairing code>`; the code is compared in constant time, stored with owner-only permissions (`0600`) in the cache directory, and replaceable from the window.
- Requests whose `Host` is not `127.0.0.1:47832` or `localhost:47832`, or that carry an `Origin` other than `chrome-extension://...`, are refused (DNS rebinding and web pages).
- Evidence limits, copied from the original behavior: body at most 256 KiB; `version == 1`; `durationMs` in 0..90000; at most 96 events, 1..48 states, 16 animations with at most 8 keyframes each, at most 4 indicators per state; every `atMs` within `0..durationMs`; `origin` is `http` or `https` with a host and no user, password, path, query or fragment.
- The latest final session is kept 180 s; a partial (streamed) session 10 s. Evidence that does not overlap the recording's wall-clock range is never attached.
- Page data is untrusted: the MCP text keeps saying so, and nothing from the page is executed or rendered as markup.
- No network beyond loopback, no telemetry, no keyboard capture (the extension reads page events only for the component the user chose). Update `README.md`, `CONTRIBUTING.md` and `AGENTS.md` for the new listener and data.
- The extension has its own name, icon and port; it does not reuse the original's name, port or artwork.
- MCP stdout is the protocol channel: no `print` in `anypoach.mcp` or what it imports.
- Commits: Conventional Commits with a scope, atomic, staged by file name, no AI attribution lines. Implementation and docs go in separate commits.
- Run the suite with `QT_QPA_PLATFORM=offscreen uv run pytest -q` and lint with `uv run ruff check src tests tools`.

## Review Focus

- A web page (not the extension) posting to `127.0.0.1:47832`, with or without a guessed code, and a rebinding host name resolving to loopback: refused (Task 2).
- A body larger than 256 KiB, a lying `Content-Length`, a slow client that stops sending, and invalid JSON: bounded and answered with the right status, never a hang of the window (Task 2).
- Port 47832 already in use: the window shows the cause and keeps working without Chrome (Task 4).
- Evidence from an earlier recording, or arriving after the 180 s window, must not attach to a new recording (Tasks 1 and 3).
- The person finishes the Chrome session after pressing Stop in AnyPoach: the final evidence still attaches when the brief is shared (Task 3).

---

### Task 1: Browser evidence validation, alignment and storage

**Files:**
- Create: `src/anypoach/bridge/__init__.py` (empty), `src/anypoach/bridge/evidence.py`
- Test: `tests/test_bridge_evidence.py`

**Interfaces:**
- Produces: `parse_evidence(raw: bytes | str | dict) -> dict` returning the validated session as a plain dict, raising `ValueError` on anything outside the Global Constraints limits; `align(evidence: dict, recording_ms: tuple[int, int]) -> dict | None` returning a copy with `videoOffsetMs = startedAtEpochMs - recording_ms[0]` when `[startedAtEpochMs, startedAtEpochMs + durationMs]` overlaps `recording_ms`, else `None`; `class EvidenceStore(clock: Callable[[], float] = time.time)` with `put(evidence: dict, final: bool) -> None`, `latest_for(recording_ms: tuple[int, int]) -> dict | None` (final sessions up to 180 s old), `receiving_for(recording_ms) -> bool` (partial session up to 10 s old, aligned), `clear() -> None`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests** in `tests/test_bridge_evidence.py` with a `session(**overrides)` helper building a valid session (one state, one event, `startedAtEpochMs=1_700_000_000_000`, `durationMs=1500`, origin `https://example.com`):
  - `test_a_valid_session_round_trips`: `parse_evidence(json.dumps(session()))` equals the dict, and a stored `videoOffsetMs` is dropped.
  - Parametrized `test_invalid_sessions_are_refused` over: version 2, `durationMs` 90001 and -1, origin with a path, origin `ftp://x`, origin with `user@`, 97 events, 0 states, 49 states, 17 animations, an animation with 9 keyframes, a state `rect` of length 3, an event `point` of length 3, an `atMs` greater than `durationMs`, bytes over 256 KiB, and non-JSON text. Each raises `ValueError`.
  - `test_align_sets_the_video_offset_when_the_ranges_overlap`: recording `(startedAt - 400, startedAt + 3000)` gives `videoOffsetMs == 400`; a recording ending before the session starts gives `None`.
  - `test_store_keeps_final_sessions_for_180_seconds`: with a fake clock, `put(final=True)` then `latest_for` is not `None` at +179 s and `None` at +181 s.
  - `test_store_reports_a_partial_session_only_while_fresh`: `receiving_for` is true right after `put(final=False)`, false after 11 s, and a partial never answers `latest_for`.
  - `test_a_newer_final_replaces_the_older_one`.
- [ ] **Step 2: Run to verify they fail**
  Run: `uv run pytest tests/test_bridge_evidence.py -q`
  Expected: FAIL (`ModuleNotFoundError: anypoach.bridge`).
- [ ] **Step 3: Implement** the module with pydantic models (strict, `extra="ignore"`, field limits as constrained types) and the cross-field checks (`atMs` ranges) in a model validator; `parse_evidence` enforces the 256 KiB byte limit before parsing and always drops `videoOffsetMs`. Unknown top-level keys such as `devicePixelRatio` and `viewport` are kept when well-typed (numbers) and ignored otherwise.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/bridge/__init__.py src/anypoach/bridge/evidence.py tests/test_bridge_evidence.py
  git commit -m "feat(bridge): validate and store browser evidence"
  ```

### Task 2: The loopback server and pairing code

**Files:**
- Create: `src/anypoach/bridge/server.py`, `src/anypoach/bridge/pairing.py`
- Test: `tests/test_bridge_server.py`, `tests/test_bridge_pairing.py`

**Interfaces:**
- Consumes: `EvidenceStore`, `parse_evidence` from Task 1.
- Produces: `pairing.load_or_create(cache: Path | None = None) -> str` (uppercase UUID4, file `bridge-pairing` in the cache directory, `0600`, a new one when the file is missing or malformed) and `pairing.rotate(cache: Path | None = None) -> str`; `BridgeServer(store: EvidenceStore, code: str, *, port: int = 47832, on_open: Callable[[], bool] | None = None)` with `start() -> None` (raises `OSError` with a readable message when the port is busy), `stop() -> None`, `port -> int` (the bound port, so tests can pass `0`), and `connected -> bool` (a valid authorized request was seen). Routes: `GET /v1/pair` 204; `POST /v1/capture` 204 with header `X-AnyPoach-Final: 1|0`; `POST /v1/open-capture` 204 when `on_open()` returns true, else 503. Statuses: 401 bad or missing bearer, 403 bad `Host` or `Origin`, 400 malformed request, 413 body over limit, 422 invalid evidence, 404 unknown path, 405 wrong method.

- [ ] **Step 1: Write the failing tests.** `tests/test_bridge_pairing.py`: creates a UUID once and returns the same on the next call; the file is `0600` on POSIX (skip on Windows); a malformed file is replaced; `rotate` returns a different code and the old one is gone. `tests/test_bridge_server.py` starts `BridgeServer(store, "CODE", port=0)` on a thread and uses `http.client` against `server.port`:
  - `test_pair_requires_the_bearer_code` (204 with it; 401 without, with a wrong one, and with the code in the query string).
  - `test_capture_is_stored_as_final_or_partial` (a valid session with `X-AnyPoach-Final: 1` makes `store.latest_for(...)` return it; with `0` only `receiving_for` is true).
  - `test_a_foreign_host_header_is_refused` (`Host: evil.example:47832` gives 403, `Host: localhost:<port>` is fine).
  - `test_a_web_page_origin_is_refused` (`Origin: https://evil.example` gives 403 even with the right code; `Origin: chrome-extension://abc` is fine; no `Origin` is fine).
  - `test_oversized_and_lying_bodies_are_bounded` (a 300 KiB body gives 413; `Content-Length` larger than the bytes sent followed by a closed socket does not hang the next request; the server answers a following request within 2 s).
  - `test_invalid_evidence_is_422_and_invalid_json_is_422`.
  - `test_a_stalled_client_is_dropped` (open a socket, send half the headers, wait past a short injected timeout, then a normal request still works).
  - `test_open_capture_uses_the_callback` (503 without one, 204 when it returns true).
  - `test_start_reports_a_busy_port` (bind a socket first; `start()` raises `OSError` whose message names the port).
  - `test_stop_releases_the_port` (stop, then bind the same port).
- [ ] **Step 2: Run to verify they fail**
  Run: `uv run pytest tests/test_bridge_pairing.py tests/test_bridge_server.py -q`
  Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** with `http.server.ThreadingHTTPServer` in a daemon thread, `BaseHTTPRequestHandler.timeout` short (5 s, constructor-overridable for tests), `hmac.compare_digest` for the code, `Host`/`Origin` checks before reading the body, body read capped at the limit plus a small margin, no CORS headers, quiet logging (nothing printed). `pairing` uses the existing `private_dir` and `write_private` helpers of `anypoach.brief`.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/bridge/server.py src/anypoach/bridge/pairing.py tests/test_bridge_server.py tests/test_bridge_pairing.py
  git commit -m "feat(bridge): serve browser evidence on loopback with a pairing code"
  ```

### Task 3: Attach the matching session to the brief

**Files:**
- Modify: `src/anypoach/analysis/types.py` (`InspectionResult.browser_evidence`, `to_json` key `browserEvidence`)
- Modify: `src/anypoach/ui/controller.py` (`Controller(..., store: EvidenceStore | None = None)`, remember the recording's `epoch_range_ms`, attach at `copy_handoff()`)
- Modify: `src/anypoach/brief/store.py` only if `share` drops the key (it must not)
- Test: `tests/test_ui_controller.py`, `tests/test_brief_store.py`

**Interfaces:**
- Consumes: `EvidenceStore.latest_for`, `EvidenceStore.receiving_for` from Task 1.
- Produces: `Controller.browser_status -> str` returning `"off"` (no store), `"waiting"`, `"receiving"` or `"attached"`; after `copy_handoff()` the brief holds `evidence["browserEvidence"]` with `videoOffsetMs` set, only when a final session overlaps the recording.

- [ ] **Step 1: Write the failing tests** in `tests/test_ui_controller.py` using the existing `LiveBackend` and a real `EvidenceStore` with a fake clock:
  - `test_a_matching_chrome_session_is_attached_to_the_brief`: record, then `store.put(session(startedAtEpochMs=recording_start + 100), final=True)`, `copy_handoff()`, and `read_brief(...)["evidence"]["browserEvidence"]["videoOffsetMs"] == 100` (use `controller.result` plus the recording range exposed for tests through the real clock: build the session from `time.time()` taken around the recording).
  - `test_chrome_finishing_after_stop_still_attaches`: the session is put after `stop()` and before `copy_handoff()`.
  - `test_a_session_from_before_the_recording_is_not_attached`: a session that ended before the recording started leaves `browserEvidence` out.
  - `test_a_stale_session_is_not_attached`: advance the fake clock 181 s after `put`.
  - `test_browser_status_follows_the_store`: `"off"` without a store; `"waiting"`; `"receiving"` after a partial; `"attached"` after a matching final and a stop.
  - In `tests/test_brief_store.py`: `test_share_keeps_browser_evidence` (a result with `browser_evidence={"version": 1, ...}` shares it under `evidence["browserEvidence"]`).
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_controller.py tests/test_brief_store.py -q -k "chrome or browser"`
  Expected: FAIL (`TypeError: ... unexpected keyword argument 'store'`).
- [ ] **Step 3: Implement.** `stop()` keeps `recording.epoch_range_ms` on the controller; `copy_handoff()` asks the store for `latest_for(range)` and, when found, returns the result with `browser_evidence` set before `share()`; `browser_status` as specified. A `None` store changes nothing for existing callers.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/analysis/types.py src/anypoach/ui/controller.py src/anypoach/brief/store.py tests/test_ui_controller.py tests/test_brief_store.py
  git commit -m "feat(ui): attach the matching Chrome session to the brief"
  ```

### Task 4: The Chrome section in the window

**Files:**
- Modify: `src/anypoach/ui/app.py` (a "Chrome" group: pairing code, "Copy code", "New code", "Open extension folder", status line; start and stop the server)
- Modify: `src/anypoach/ui/app.py` `main()` (create `EvidenceStore`, load the code, build `BridgeServer`, pass the store to `Controller`)
- Test: `tests/test_ui_window.py`

**Interfaces:**
- Consumes: `BridgeServer`, `pairing.load_or_create`/`rotate`, `Controller.browser_status`; `extension_dir() -> Path` (add to `anypoach.bridge` in this task: the folder of the packaged extension, via `importlib.resources.files("anypoach") / "chrome_extension"`).
- Produces: `MainWindow(controller, bridge: BridgeController | None = None)` where `BridgeController` is a small Qt-free class in `anypoach.bridge.control` with `code -> str`, `rotate() -> str`, `status -> str` (`"stopped"`, `"listening"`, `"error: <message>"`), `start()`, `stop()`; the window shows the code in a read-only field, buttons with accessible names ("Copy pairing code", "Create a new pairing code", "Open the extension folder"), and the status text.

- [ ] **Step 1: Write the failing tests.** `tests/test_bridge_control.py`: `start()` on a free port reports `listening`; with the port taken it reports `error:` containing the port and does not raise; `rotate()` changes the code the running server accepts (old code gets 401, new gets 204); `stop()` frees the port. `tests/test_ui_window.py` with a fake `BridgeController`: the code field shows the code and is read-only; "Copy pairing code" puts it on the clipboard; "Create a new pairing code" updates the field; every new control has an accessible name; an `error:` status is visible in the window and the Record button still works; closing the window calls `stop()`.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_bridge_control.py tests/test_ui_window.py -q -k "bridge or chrome or pairing"`
  Expected: FAIL.
- [ ] **Step 3: Implement** `BridgeController` and the window section; "Open the extension folder" uses `QDesktopServices.openUrl(QUrl.fromLocalFile(...))` and shows a message when the folder is missing. `main()` starts the server and shows a port error in the status line instead of failing.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/bridge/control.py src/anypoach/bridge/__init__.py src/anypoach/ui/app.py tests/test_bridge_control.py tests/test_ui_window.py
  git commit -m "feat(ui): show the Chrome pairing code and server status"
  ```

### Task 5: The extension

**Files:**
- Create: `src/anypoach/chrome_extension/manifest.json`, `bridge.js`, `capture.js`, `popup.html`, `popup.css`, `popup.js`, `icon.png`
- Create: `tools/make_extension_icon.py` (writes the icon with the standard library; the artwork is ours, a plain geometric mark)
- Modify: `pyproject.toml` (include the extension folder in the wheel)
- Test: `tests/test_chrome_extension.py`, `tests/chrome/bridge_flow.mjs`, `tests/chrome/capture_page.html`

**Interfaces:**
- Consumes: the server routes and statuses of Task 2; the evidence shape of Task 1.
- Produces: an unpacked MV3 extension named AnyPoach (`host_permissions`: `http://127.0.0.1/*` only; permissions `activeTab`, `scripting`, `storage`), messages namespaced `anypoachBridge` and `anypoach`, base URL `http://127.0.0.1:47832/v1`, header `X-AnyPoach-Final`, pairing code regex for an uppercase UUID. The snapshot adds two optional numbers, `devicePixelRatio` and `viewport: {width, height}`, taken from the page.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_chrome_extension.py::test_manifest_is_minimal_and_ours`: parses `manifest.json`; version 3; name `AnyPoach`; `host_permissions == ["http://127.0.0.1/*"]`; no `<all_urls>`; the service worker is `bridge.js`; every file it references exists; no string `Poach` outside `AnyPoach` appears in any extension file.
  - `::test_the_wheel_ships_the_extension`: build the wheel into a temp dir (skip if `uv` is missing) and check the extension files are inside.
  - `::test_bridge_flow_against_the_real_server` (skipped without `node`): starts `BridgeServer(store, code, port=0)` on a thread and runs `node tests/chrome/bridge_flow.mjs <port> <code>`. The script stubs `globalThis.chrome` (`storage.local`, `runtime.onMessage`, `runtime.id`) and wraps `fetch` to swap `:47832` for the test port, imports `bridge.js`, then sends: a pairing message (wrong code gives an error reply, right code gives ok and stores it), a `capture` message with a valid session and `final: true` (the store then returns it), an oversized evidence (error reply, nothing sent), and a `capture` while the server answers 401 (reply asks to pair again).
  - `::test_capture_script_records_a_component_in_headless_chrome` (skipped without Chrome): serves `tests/chrome/capture_page.html` (a button whose width and background change on hover through a CSS transition, a stub `chrome` object that collects messages), runs `google-chrome --headless=new --dump-dom` with a virtual time budget, and asserts from the dumped DOM that the final snapshot has `version == 1`, a `states` list whose last `rect` width is larger than the first, `animations` or `events` containing `transitionrun`, an `origin` of the page, and the optional `devicePixelRatio`.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_chrome_extension.py -q`
  Expected: FAIL (files missing).
- [ ] **Step 3: Implement** by adapting the original extension's behavior (select a component with pointer or keyboard, sample computed styles and rect every 100 ms and on `transitionrun`/`animationstart`, record up to 96 events and 16 animations, stream a partial snapshot every second and a final one on finish, 90 s cap) to this plan's names; write `bridge.js` with the queueing behavior (a slow connection may drop partial snapshots, the final one carries everything). The popup text says AnyPoach and where to find the pairing code. Generate `icon.png` with `tools/make_extension_icon.py`. Add the folder to the wheel with the build backend's include setting.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS (the Node and Chrome tests are skipped, with a visible reason, where those tools are missing).
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/chrome_extension tools/make_extension_icon.py pyproject.toml tests/test_chrome_extension.py tests/chrome
  git commit -m "feat(chrome): add the AnyPoach companion extension"
  ```

### Task 6: Teach the assistant to prefer the browser's numbers

**Files:**
- Modify: `src/anypoach/mcp/server.py` (`_Styles` gains layout and paint keys, `_BrowserState` keeps `rect`, a new `_BrowserAnimation`, `_browser_near` includes animations, the page's `devicePixelRatio` and `viewport`)
- Modify: `src/anypoach/mcp/descriptions.py` (the two tool descriptions mention the new fields)
- Modify: `src/anypoach/ui/controller.py` (`handoff_prompt` gains a sentence on browser evidence)
- Test: `tests/test_mcp_server.py`, `tests/test_ui_controller.py`

**Interfaces:**
- Consumes: `evidence.browserEvidence` as stored by Task 3.
- Produces: in `anypoach_read_moment`, the "Nearby Chrome evidence" line lists, for each item near the moment, `rect` (`[x, y, width, height]` in CSS pixels), the style keys `width`, `height`, `borderRadius`, `opacity`, `transform`, `color`, `backgroundColor`, `boxShadow` besides the typography ones, animations with `durationMs`, `delayMs`, `easing` and keyframe offsets, and a header with `devicePixelRatio` and `viewport` when present. Models stay `extra="ignore"` so older sessions still parse.

- [ ] **Step 1: Write the failing tests.** In `tests/test_mcp_server.py`: a brief with `browserEvidence` (one state with `rect [10, 20, 240.5, 48]` and styles including `width: "240.5px"`, `borderRadius: "12px"`; one animation `durationMs 334`, `easing "cubic-bezier(0.16, 0.9, 0.3, 1)"`; `devicePixelRatio 2`; `viewport {width: 1280, height: 720}`) read through `anypoach_read_moment` near the right video time returns text containing `"rect"`, `"240.5px"`, `"borderRadius"`, `"334"`, the easing string, and `devicePixelRatio`; the existing typography test keeps passing; a session whose animation entry is malformed is skipped without an error. In `tests/test_ui_controller.py::test_handoff_prompt_prefers_browser_evidence`: the prompt mentions `evidence.browserEvidence` and says its values win over measurements from the video.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_mcp_server.py tests/test_ui_controller.py -q -k "browser"`
  Expected: FAIL.
- [ ] **Step 3: Implement** the model and line changes and the prompt sentence ("When `evidence.browserEvidence` is present, its CSS sizes, typography and animation timing come from the page itself: use them instead of measuring the video, and use the video to confirm the result"). Keep the bound of 12 items near a moment.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/mcp/server.py src/anypoach/mcp/descriptions.py src/anypoach/ui/controller.py tests/test_mcp_server.py tests/test_ui_controller.py
  git commit -m "feat(mcp): prefer the page's own sizes and animation timing"
  ```

### Task 7: Documentation

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `docs/superpowers/poach-parity.md`

- [ ] **Step 1: Write the docs.** README: a "Chrome companion" subsection under Usage (load the unpacked folder through "Open the extension folder", pair, choose a component, record, press "Finish and send"), what the assistant receives and what stays local, the port and loopback-only listener, Edge and Brave work too, and the honest status (no store listing yet). CONTRIBUTING: the manual check (pair, select a hover on a real page, record, finish in Chrome after stopping in AnyPoach, read the brief back and see `browserEvidence` with `videoOffsetMs`; a wrong code and a busy port show clear messages) and how to run the Node and Chrome tests. AGENTS.md: the loopback listener and the evidence data are covered by the privacy rule, and only run while the window is open. CLAUDE.md: the `bridge` package in the architecture list and its gotchas. `poach-parity.md`: mark the Chrome row as done in v0.2a. Any mention of the original follows the AGENTS.md rule (docs only, warm mockery, never in code).
- [ ] **Step 2: Verify the commands** in the new text against the code (port, folder name, button names) and run `uv run ruff check src tests tools && QT_QPA_PLATFORM=offscreen uv run pytest -q`.
  Expected: clean, all pass.
- [ ] **Step 3: Commit**
  ```bash
  git add README.md CONTRIBUTING.md AGENTS.md CLAUDE.md docs/superpowers/poach-parity.md
  git commit -m "docs(chrome): document the companion extension and its privacy"
  ```

## Self-Review

- **Spec coverage (Chrome section):** extension (Task 5), server with pairing and limits (Task 2), evidence kept 180 s and aligned (Tasks 1 and 3), brief key and MCP reading (Tasks 3 and 6), prompt (Task 6), window section with the folder button (Task 4), privacy and docs (Task 7). Not here: Chrome Web Store, macOS items, motion segments, phase 2b.
- **Rulings already made in this plan:** the brief key is the existing `browserEvidence` (the spec said `evidence.browser`, and the server already reads the former); the session attaches at `copy_handoff()` rather than at `stop()`, so finishing in Chrome after pressing Stop still works; the pairing code is an uppercase UUID; `devicePixelRatio` and `viewport` are additive and optional.
- **Types:** `EvidenceStore`, `parse_evidence`, `align`, `BridgeServer`, `BridgeController` and `Controller.browser_status` carry the same names and signatures in every task that uses them.
