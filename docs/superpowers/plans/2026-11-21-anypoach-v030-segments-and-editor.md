# AnyPoach v0.3.0: Motion Segments and Comment Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A recording with several interactions is described interaction by interaction, and the person who recorded it can review the video, pin comments to any moment and write general instructions that reach the assistant.

**Architecture:** `analysis/segments.py` splits the frame-to-frame difference series into motion segments and `inspect_video` runs the existing `choose_keyframes` and timing code on each one, leaving the top-level `keyframes` and `timing` computed exactly as today. A Qt-free `analysis/proxy.py` decodes the recording once into small JPEG frames with real presentation times; a timeline widget and a review panel in the window scrub and play those frames and write comments through new `Controller` methods into the `annotations` and `context` the brief already carries.

**Tech Stack:** Python 3.11+, PyAV (decode, and its `mjpeg` encoder for the proxy), numpy, PySide6, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-21-anypoach-v030-segments-and-editor-design.md` (read it with this plan; it holds the reasons). Parent designs: `2026-11-21-anypoach-fidelity-design.md` (Design B) and `2026-11-21-anypoach-phase2-design.md`.

## Global Constraints

- The top-level `keyframes` and `timing` of every `InspectionResult` stay computed over the whole delta series by the same code as today. Files in `tests/golden` are not edited.
- Brief `version` stays `1`. Briefs without `segments` are read without error. New fields are optional.
- Segment constants, starting values: active when a delta is at least `0.008`; runs closer than `400` ms merge; `250` ms of slack after a segment; at most `12` segments (the strongest by peak); PNGs only for the `4` strongest.
- Proxy: longest side `640` px, `15` frames per second, JPEG quality via PyAV `mjpeg` (`qscale` 4), held in memory only, never written to disk or sent anywhere.
- Comments: at most `500` characters each (after stripping), at most `50` per recording, empty text refused with a message. A new recording clears comments and keeps the general instructions.
- No network, telemetry or retention beyond the brief's existing 24 h expiry (`AGENTS.md`). MCP stdout is the protocol channel: no `print` in `anypoach.mcp` or what it imports.
- Every control has an accessible name and the review panel is operable by keyboard alone.
- Docstrings in Google style, line length 110. Commits: Conventional Commits with a scope, atomic, staged by file name, no AI attribution lines; implementation and docs in separate commits.
- Run the suite with `QT_QPA_PLATFORM=offscreen uv run pytest -q` and lint with `uv run ruff check src tests tools`. The suite needs the `ffmpeg` CLI only to synthesize clips.
- README and CONTRIBUTING are updated in Task 8 (the window gains a feature and a data path).

## Review Focus

- A one-interaction clip with residual motion (a cursor, a caret) above the `0.008` floor: the top-level `keyframes` and `timing` must not change even though `segments` may hold more than one entry. Pinned in Task 2.
- A small hover separated in time from a big movement must become its own segment with its own timing, and two movements closer than 400 ms must stay one. Pinned in Tasks 1 and 2.
- More than 12 segments, more than 4 with images, and the strongest segment's PNGs not repeated in `anypoach_read_brief`. Pinned in Tasks 2 and 3.
- A comment's `timeMs` must be a moment `anypoach_read_moment` resolves to the frame the person saw. Pinned in Tasks 4 and 5.
- Starting a new recording, or closing the window, while the proxy is still decoding: the worker stops, nothing raises, no thread outlives the window. Pinned in Tasks 4 and 7.
- Comment text at its edges: whitespace only, exactly 500 and 501 characters, accents and emoji, the 50th and 51st comment. Pinned in Task 5.

---

## File Structure

- Create `src/anypoach/analysis/segments.py`: pure detection of motion segments from deltas and times.
- Create `src/anypoach/analysis/proxy.py`: Qt-free decoding of the recording into small JPEG frames.
- Create `src/anypoach/ui/timeline.py`: `group_markers` (pure) and `TimelineWidget`.
- Modify `src/anypoach/analysis/types.py` (`MotionSegment`, `InspectionResult.segments`), `analysis/inspect.py`, `brief/store.py`, `mcp/server.py`, `ui/controller.py`, `ui/app.py`.
- Modify `tests/fixtures.py` (a multi-interaction clip builder).
- Tests: `tests/test_segments.py`, `tests/test_inspect_segments.py`, `tests/test_proxy.py`, `tests/test_timeline.py`, additions to `tests/test_mcp_server.py`, `tests/test_brief_store.py`, `tests/test_ui_controller.py`, `tests/test_ui_window.py`.

---

### Task 1: Segment detection

**Files:**
- Create: `src/anypoach/analysis/segments.py`
- Test: `tests/test_segments.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class SegmentSpan`: `start: int`, `end: int`, `peak: int`, `strength: float`. All three indices are frame indices; `deltas[i]` is the change into frame `i + 1`, so the frames of a span are `start..end` inclusive and `peak` is the frame before the largest change (the same convention as `choose_keyframes`).
  - `find_segments(deltas: Sequence[float], times_ms: Sequence[int], *, floor: float = 0.008, merge_ms: int = 400, slack_ms: int = 250) -> list[SegmentSpan]`, in time order, with `len(times_ms) == len(deltas) + 1`.

- [ ] **Step 1: Write the failing tests in `tests/test_segments.py`** with hand-made delta series at 12 samples per second (`times_ms[i] = round(i * 1000 / 12)`): `test_a_static_series_has_no_segments` (all zeros and all `0.007`), `test_one_burst_is_one_span_with_slack` (a burst of deltas at indices 10 to 15, expect `start == 10`, `end` at the last frame whose time is at most 250 ms past frame 16, `peak` at the index of the largest delta, `strength` equal to it), `test_bursts_300_ms_apart_merge_and_500_ms_apart_do_not`, `test_a_small_hover_next_to_a_big_movement_is_its_own_span` (a burst of `0.2` at 10 to 14 and a burst of `0.01` at 60 to 62: two spans, the second with `strength == 0.01`), `test_spans_never_overlap_and_stay_inside_the_clip` (a burst at the very first and the very last delta), `test_one_sample_is_enough_to_start_a_span`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_segments.py -v`
Expected: FAIL with `ModuleNotFoundError: anypoach.analysis.segments`.

- [ ] **Step 3: Implement `find_segments`** in the order: collect runs of consecutive deltas at or above `floor`; merge runs when `times_ms[next.first_delta] - times_ms[prev.last_delta + 1] < merge_ms`; a span runs from the first delta index of the run to the last frame whose time is at most `times_ms[last_delta + 1] + slack_ms` (clamped to the last frame, and to just before the next span's start); `peak` is the argmax of the deltas inside the run (first one on ties); `strength` is that delta.

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/test_segments.py -v && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/analysis/segments.py tests/test_segments.py
git commit -m "feat(analysis): split motion into segments"
```

---

### Task 2: Segments in the analysis result

**Files:**
- Modify: `src/anypoach/analysis/types.py`, `src/anypoach/analysis/inspect.py`, `tests/fixtures.py`
- Test: `tests/test_inspect_segments.py`

**Interfaces:**
- Consumes: `find_segments`, `SegmentSpan` (Task 1); `choose_keyframes(deltas, count)`, `approximate_timing`, `Keyframe`, `MotionTiming`.
- Produces:
  - `@dataclass(frozen=True) class MotionSegment` in `types.py`: `start_ms: int`, `peak_ms: int`, `end_ms: int`, `strength: float`, `timing: MotionTiming`, `keyframes: list[Keyframe]`, with `to_json()` returning `{"startMs", "peakMs", "endMs", "strength", "timing": {"durationMs", "bezier", "token"}, "keyframes": [...]}` (keyframes serialized like the top level's, `motion` included; `share` strips it in Task 3).
  - `InspectionResult.segments: list[MotionSegment] | None = None`, serialized under `"segments"` whenever it is not None (an empty list for a clip with no motion; None for images).
  - `build_multi(directory: Path, bursts: list[tuple[float, float, int]]) -> Path` in `tests/fixtures.py`: a 160x90, 30 fps, black clip with one orange box of a given size per burst; each `(start_s, duration_s, box_px)` makes a box ease across the frame during that window, using the same expression style as the `motion` clip. The clip lasts until 1 s after the last burst.

- [ ] **Step 1: Add `build_multi` to `tests/fixtures.py` and write the failing tests** in `tests/test_inspect_segments.py` (a module-scoped fixture builds the clips with `ffmpeg`, skipping the module when it is missing, like `tests/test_inspect_golden.py` does):
  - `test_a_clip_with_one_interaction_has_one_segment_and_the_top_level_is_unchanged`: the `motion` clip's `keyframes` and `timing` equal today's values from `tests/golden/motion.json`, and `segments` has one entry whose `keyframes` have the same paths as the top level's.
  - `test_three_bursts_make_three_segments_in_time_order`.
  - `test_a_small_burst_after_a_big_one_is_its_own_segment_with_its_own_timing` (bursts `(0.5, 0.6, 40)` and `(4.0, 0.4, 6)`).
  - `test_the_top_level_is_the_strongest_segment_and_shares_its_files`.
  - `test_more_than_twelve_bursts_keep_the_twelve_strongest_and_images_for_four` (14 bursts of different box sizes: `len(segments) == 12`, exactly 4 segments with non-empty `keyframes`, those being the 4 strongest, and PNGs on disk only for them).
  - `test_residual_motion_does_not_change_the_top_level` (the `motion` clip plus a tiny second burst `(1.5, 0.3, 3)`: top-level equals the `motion` golden result, `segments` may have two entries).
  - `test_a_static_clip_has_no_segments_and_a_start_keyframe` and `test_an_image_has_segments_none`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_inspect_segments.py -v`
Expected: FAIL (`segments` attribute missing).

- [ ] **Step 3: Implement.** In `types.py` add `MotionSegment` and the optional `segments` field with its JSON. In `inspect.py`: factor the "keys to timing" step that `inspect_video` does for the whole clip into one helper (`_timing_for(times_ms, deltas, keys, duration_s) -> tuple[int, MotionTiming]`) and use it for the whole clip and for each segment, so there is one copy of that logic. For each span from `find_segments`, run `choose_keyframes(deltas[span.start:span.end], span.end - span.start + 1)` and shift the returned indices by `span.start`. Keep the strongest 12 spans by `strength`, then restore time order. The span with the largest `strength` takes the top-level `keyframes` list and `timing` as they are (same objects, same files); write PNGs named `{base}-s{n}-{kind}-{ms}ms.png` only for the next 3 strongest; the rest get `keyframes=[]`. `progress("frames")` is called once, before any PNG is written, as today.

- [ ] **Step 4: Run the whole suite, including the unchanged goldens**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS, with no change under `tests/golden`.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/analysis/types.py src/anypoach/analysis/inspect.py tests/fixtures.py tests/test_inspect_segments.py
git commit -m "feat(analysis): describe each motion segment with its own keyframes and timing"
```

---

### Task 3: Segments in the brief, the MCP tool and the prompt

**Files:**
- Modify: `src/anypoach/brief/store.py`, `src/anypoach/mcp/server.py`, `src/anypoach/ui/controller.py`
- Test: `tests/test_brief_store.py`, `tests/test_mcp_server.py`, `tests/test_ui_controller.py`

**Interfaces:**
- Consumes: `InspectionResult.segments` (Task 2).
- Produces: `share()` writes `evidence.segments` with each keyframe's `motion` removed, like the top level; `anypoach_read_brief` returns, when `segments` exists, the images of the segments that have them in time order (at most 12) and skips any whose `imagePath` already went out as a top-level keyframe; `handoff_prompt` gains the multi-interaction sentence below.

- [ ] **Step 1: Write the failing tests:**
  - `test_brief_store.py::test_segments_are_stored_without_motion`.
  - `test_mcp_server.py::test_read_brief_returns_segment_images_in_time_order_without_repeats` (a brief whose top-level keyframes are the strongest segment's: each PNG is returned once), `test_read_brief_allows_up_to_twelve_images_and_refuses_more`, `test_a_brief_without_segments_is_read_as_before`, `test_segment_json_reaches_the_structured_content`.
  - `test_ui_controller.py::test_handoff_prompt_warns_about_several_interactions`: the prompt contains the exact sentence `"A recording may hold several interactions: each segment in evidence.segments has its own timing, so never read one segment's timing as another's."`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_brief_store.py tests/test_mcp_server.py tests/test_ui_controller.py -k "segment or interactions" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the three changes. In `read_brief` replace the fixed "more than 3" refusal with a limit of 12 images per response; the top-level `keyframes` of a stored brief are still validated with the existing `Frame` model, and segment keyframes use the same model. Add the sentence to `handoff_prompt` before the pointer guidance.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/brief/store.py src/anypoach/mcp/server.py src/anypoach/ui/controller.py tests/test_brief_store.py tests/test_mcp_server.py tests/test_ui_controller.py
git commit -m "feat(mcp): hand the assistant every motion segment"
```

---

### Task 4: The frame proxy

**Files:**
- Create: `src/anypoach/analysis/proxy.py`
- Test: `tests/test_proxy.py`

**Interfaces:**
- Consumes: `VideoSource` (`duration_s`, `presentation_times`, `seek_for_moment`, `frames_at(seeks, width)`, `size`).
- Produces:
  - `@dataclass(frozen=True) class ProxyFrame`: `time_ms: int` (presentation time from the start of the video, the axis of `anypoach_read_moment`), `jpeg: bytes`.
  - `class FrameProxy`: `frames: list[ProxyFrame]` (time order), `done: bool`, `duration_ms: int`, `nearest(time_ms: int) -> ProxyFrame | None` (the frame whose `time_ms` is closest, ties to the earlier one; None while empty), `step(from_ms: int, direction: int) -> ProxyFrame | None` (the neighbor frame, None past either end).
  - `build_proxy(path: str | Path, *, cancel: threading.Event, on_frame: Callable[[ProxyFrame], None] | None = None, rate: float = 15, max_side: int = 640) -> FrameProxy`: decodes in time order, calls `on_frame` for each frame as it is ready, checks `cancel` before every frame and returns the partial proxy (`done == False`) when it is set. Raises `ValueError` like `VideoSource` on an unreadable file.

- [ ] **Step 1: Write the failing tests** on the `motion` clip from `tests/fixtures.py` (2 s, 30 fps): `test_frames_arrive_in_time_order_at_the_requested_rate` (about 30 frames at 15 fps, times strictly increasing, the first at 0), `test_every_frame_is_a_jpeg_within_the_size_limit` (decode a frame with PyAV, longest side at most 640, and for the `wide` clip, 1600 px wide, exactly 640), `test_nearest_and_step`, `test_a_set_cancel_stops_before_decoding_everything_and_leaves_done_false`, `test_on_frame_is_called_once_per_frame_in_order`, `test_a_proxy_time_resolves_to_the_same_frame_as_read_moment` (take a proxy frame's `time_ms`, call `read_video_moment(path, time_ms)` from `analysis.inspect`, decode the proxy JPEG, and check the mean absolute pixel difference of the two images after resizing to the smaller size is under 6 of 255), and `test_an_unreadable_file_is_a_value_error`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement.** Choose the sample times as `i / rate` seconds up to the duration, resolve each with `source.seek_for_moment`, decode in batches of about 16 with `frames_at(seeks, width)` (width from `max_side` and the aspect ratio, never enlarging), and encode each array with a PyAV `mjpeg` `CodecContext` (`pix_fmt="yuvj420p"`, `options={"qscale": "4"}`). `time_ms` is the rounded sample time. If the PyAV build in CI lacks the `mjpeg` encoder, fall back to the existing `encode_png` at the same size and say so in the module docstring; the tests accept either through `ProxyFrame.jpeg` being decodable by PyAV.

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/test_proxy.py -v && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/analysis/proxy.py tests/test_proxy.py
git commit -m "feat(analysis): decode a recording into small frames for the editor"
```

---

### Task 5: Comments and general instructions in the controller

**Files:**
- Modify: `src/anypoach/ui/controller.py`
- Test: `tests/test_ui_controller.py`

**Interfaces:**
- Produces on `Controller`: `add_comment(time_ms: int, text: str) -> bool` (False with `message` set when the stripped text is empty, longer than 500 characters, or the recording already has 50 comments), `remove_comment(index: int) -> None` (an out-of-range index is ignored), `comments -> list[dict[str, Any]]` (a copy, sorted by `timeMs`, each `{"timeMs": int, "text": str}`), and `annotations` stays the list `share()` reads, kept equal to `comments` by these methods. `start()` clears the comments and keeps `context`.

- [ ] **Step 1: Write the failing tests:** `test_a_comment_is_stored_sorted_and_shared_in_the_brief` (two comments added out of order, `copy_handoff()`, `read_brief` shows them sorted under `evidence.annotations`), `test_empty_and_whitespace_comments_are_refused_with_a_message`, `test_comment_length_is_limited_to_500_characters_after_stripping` (500 accepted, 501 refused, 500 with surrounding spaces accepted), `test_the_fifty_first_comment_is_refused`, `test_accents_and_emoji_survive_the_round_trip`, `test_removing_a_comment_by_index_and_an_out_of_range_index_is_ignored`, `test_a_new_recording_clears_comments_but_keeps_the_instructions`, `test_comments_and_instructions_reach_the_brief_the_mcp_reads` (read back with `read_brief`, check `context` and `evidence.annotations`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_ui_controller.py -k comment -v`
Expected: FAIL (`add_comment` missing).

- [ ] **Step 3: Implement** the three methods, the two limits as module constants `MAX_COMMENT_CHARS = 500` and `MAX_COMMENTS = 50`, and the clearing in `start()` (after the refusal checks, so a refused start keeps them).

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/controller.py tests/test_ui_controller.py
git commit -m "feat(ui): keep timestamped comments and general instructions in the controller"
```

---

### Task 6: The timeline widget

**Files:**
- Create: `src/anypoach/ui/timeline.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- Consumes: `FrameProxy` (Task 4), the segments' `startMs`/`endMs` (Task 2).
- Produces:
  - `group_markers(times_ms: Sequence[int], duration_ms: int, width_px: int, min_gap_px: int = 24) -> list[tuple[int, list[int]]]`: markers whose pixel positions are closer than `min_gap_px` are grouped; each result is `(x_px, [indices into times_ms])`, left to right.
  - `class TimelineWidget(QWidget)` with `set_duration(duration_ms: int)`, `set_segments(spans: list[tuple[int, int]])`, `set_comments(times_ms: list[int])`, `set_position(time_ms: int)`, signal `position_requested(int)` (emitted with a millisecond time when the person drags or clicks the track, or presses Left or Right, the host snaps it to a frame), signal `marker_activated(list)` (the comment indices of a clicked marker group), accessible name `"Timeline"`.

- [ ] **Step 1: Write the failing tests:** `test_group_markers` (markers 10 px apart group, 30 px apart stay apart, three close ones give one group of three at the first one's position, an empty list gives `[]`, a zero duration does not divide by zero), `test_clicking_the_track_emits_the_time_under_the_pointer` (offscreen widget of known width, `QTest.mouseClick`), `test_dragging_emits_repeatedly_and_clamps_to_the_ends`, `test_arrow_keys_emit_a_step_request_around_the_current_position`, `test_clicking_a_marker_emits_its_comment_indices`, `test_the_widget_has_an_accessible_name_and_takes_focus`.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_timeline.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `group_markers` and the widget.** The widget paints in `paintEvent` (track, segment bands behind, markers with a count when grouped, a playhead line) and maps `x` to time linearly across its width minus a small margin. Arrow keys emit `position_requested` with the current position plus or minus one nominal frame (`1000 / 15` ms); the host decides the real neighbor.

- [ ] **Step 4: Run the tests and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_timeline.py -v && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/timeline.py tests/test_timeline.py
git commit -m "feat(ui): add the timeline with grouped comment markers"
```

---

### Task 7: The review panel in the window

**Files:**
- Modify: `src/anypoach/ui/app.py`
- Test: `tests/test_ui_window.py`

**Interfaces:**
- Consumes: `build_proxy`, `FrameProxy`, `ProxyFrame` (Task 4); `TimelineWidget` (Task 6); `Controller.add_comment`, `remove_comment`, `comments`, `context`, `result` (Task 5); `result.segments` (Task 2).
- Produces on `MainWindow`: a review panel shown after a successful stop with a frame display (`QLabel`, accessible name `"Recording frame"`), the timeline, a play/pause button (`"Play"` or `"Pause"` as its accessible name), a comment field (`"Comment"`), an add button (`"Comment at this moment"`), a comment list (`"Comments"`) whose items have a remove control, and a general-instructions field (`"General instructions"`) bound to `controller.context`; test hooks: `window.review.playhead_ms` and `window.review.proxy`.

- [ ] **Step 1: Write the failing tests** (offscreen, with a fake controller exposing `result` with `segments`, a tiny real clip for the proxy, and an injected play timer and clock so nothing waits in real time): `test_the_panel_appears_after_a_stop_with_a_result_and_every_control_is_named`, `test_the_comment_button_is_off_until_a_frame_is_ready_and_on_after`, `test_scrubbing_snaps_to_a_proxy_frame_and_shows_it`, `test_adding_a_comment_uses_the_frame_time_and_lists_it_sorted`, `test_clicking_a_comment_pauses_seeks_and_highlights_for_three_seconds` (injected clock), `test_removing_a_comment_updates_the_list_and_the_timeline_markers`, `test_play_advances_through_the_frames_and_stops_at_the_end`, `test_space_toggles_play_and_the_arrows_step_one_frame`, `test_general_instructions_reach_the_controller`, `test_starting_a_new_recording_cancels_the_proxy_worker_and_clears_the_panel`, `test_closing_the_window_cancels_the_worker_and_leaves_no_thread_running`, `test_copy_handoff_works_while_the_proxy_is_still_decoding`, `test_a_comment_time_is_one_read_moment_resolves_to_the_frame_that_was_shown` (pick a comment time from the panel, call `read_video_moment` at it and compare with the shown proxy frame within a small pixel tolerance).

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_window.py -k "review or comment or proxy or panel or play" -v`
Expected: FAIL.

- [ ] **Step 3: Implement.** After `controller.stop()` returns a result, start a worker thread (`threading.Thread`, daemon, with a `threading.Event` for cancel) that runs `build_proxy(result.source_path, cancel=event, on_frame=...)`; `on_frame` hands each frame to the GUI thread through a Qt signal. Show the first frame as soon as it arrives. Playback is a `QTimer` at the proxy's nominal interval stepping with `FrameProxy.step`. Highlighting uses a `QTimer.singleShot` whose delay and clock are injectable. Cancel and join the worker (with a short timeout) in `closeEvent` and before a new recording starts. Keep the keyframe strip, shown as a list under the player.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anypoach/ui/app.py tests/test_ui_window.py
git commit -m "feat(ui): review the recording and comment on any moment"
```

---

### Task 8: Docs, manual checks, version

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `docs/superpowers/poach-parity.md`, `pyproject.toml`, `src/anypoach/chrome_extension/manifest.json`, `src/anypoach/mcp/server.py`, `uv.lock`

- [ ] **Step 1: README.** Replace "Not done: comment editor" with what now exists; add the review panel, comments and general instructions to Usage; add `evidence.segments` to Key Outputs; keep the platform status honest about what no person has run.

- [ ] **Step 2: CONTRIBUTING.** Add to "Manual checks": record 20 s with three separate interactions and check `evidence.segments` has three entries with sensible timing and that `anypoach_read_brief` returns their images; the panel shows the first frame within a second of stopping on a 1080p area, scrubbing is smooth, play does not stutter badly, a comment at 12.3 s shows the same frame through `anypoach_read_moment`, and starting a new recording or closing the window while frames are still preparing leaves nothing running: the process exits promptly. Add `analysis/segments.py` and `analysis/proxy.py` to the data-handling note: frames are held in memory only.

- [ ] **Step 3: AGENTS.md and CLAUDE.md.** Add the new modules and the rule that the top-level result is computed on the whole series. Roadmap in `poach-parity.md`: v0.3.0 content as built, v0.4.0 as the rest of the 2b plus adjustable palette, v0.5.0 packaging.

- [ ] **Step 4: Manual checks and version.** A person runs the checks of Step 2 on a real desktop and the result goes in the PR description; anything not run is listed as not run. Then bump to `0.3.0` in `pyproject.toml`, `manifest.json` and `server.py` and refresh `uv.lock`.

- [ ] **Step 5: Run everything**

Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
Expected: PASS; CI green on Ubuntu, Windows and macOS.

- [ ] **Step 6: Commit docs and version separately**

```bash
git add README.md CONTRIBUTING.md AGENTS.md CLAUDE.md docs/superpowers/poach-parity.md
git commit -m "docs(editor): document segments, the review panel and the manual checks"
git add pyproject.toml src/anypoach/chrome_extension/manifest.json src/anypoach/mcp/server.py uv.lock
git commit -m "chore(release): prepare v0.3.0"
```

Tag and release only after the maintainer says so.
