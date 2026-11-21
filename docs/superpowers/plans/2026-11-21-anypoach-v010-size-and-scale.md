# AnyPoach v0.1.0: Capture Size and Scale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell the assistant the real size and scale of a capture, so a 1854x962 recording that reaches it as a 1280x664 image is no longer measured as if it were 1280 px wide.

**Architecture:** `InspectionResult` gains an optional `capture` (native width, height, device scale, image reduction limit) that `share()` writes to `evidence.capture`. The MCP server writes a size caption before every image it returns, and `anypoach_read_moment` accepts `maxSize` and `crop` (native pixels, applied before reduction) so a detail can be read at native scale. The handoff prompt explains both. The brief version stays `1`; every new field is optional.

**Tech Stack:** Python 3.11+, PyAV, numpy, pydantic (MCP server), PySide6, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-21-anypoach-fidelity-design.md` (section "Design A: tamanho e escala").

## Global Constraints

- MCP stdout is the protocol channel: never `print` in `anypoach.mcp` or what it imports.
- Each image the MCP returns stays at or under 5 MB (`FIVE_MB`); `maxSize` never enlarges a frame.
- `evidence.capture` is optional: a brief without it (every brief written before this change) is read without error and its images get no scale note.
- `deviceScale` is `null` when unknown (Wayland portal, imported media). Never default it to 1.0.
- The default `maxSize` stays 1280, the same as today's keyframes.
- Text returned by the MCP server is English, like the rest of it.
- Commits: Conventional Commits with a scope, atomic, staged by file name, no AI attribution lines. Implementation and docs go in separate commits.
- Run the suite with `QT_QPA_PLATFORM=offscreen uv run pytest -q` and lint with `uv run ruff check src tests tools`.

## Review Focus

- A crop that is empty, negative, or reaches outside the native frame: a clear `ValueError` message, never a crash or a blank image (Task 4).
- A brief written before this change, with no `capture`: `anypoach_read_brief` and `anypoach_read_moment` still work and write no scale note (Task 3).
- An odd native size such as 1853x961: the caption states the exact native size and a scale rounded to two decimals, never a size that is off by one (Tasks 1 and 3).
- A still-image brief: it also carries `capture`, with `deviceScale` null (Task 1).
- A crop plus `maxSize` whose PNG is over 5 MB: refused with a message that suggests a smaller crop (Task 4).

---

### Task 1: Native size and scale in the analysis result

**Files:**
- Modify: `src/anypoach/analysis/types.py` (new `CaptureInfo`, `InspectionResult.capture`, `to_json`)
- Modify: `src/anypoach/analysis/source.py` (`VideoSource.size`)
- Modify: `src/anypoach/analysis/inspect.py` (`inspect_video`, `inspect_image` fill `capture`)
- Modify: `tests/fixtures.py` (a `wide` clip, 1600x900, 1 s)
- Test: `tests/test_inspect_golden.py`, `tests/test_source.py`

**Interfaces:**
- Produces: `CaptureInfo(width_px: int, height_px: int, device_scale: float | None = None, image_max_size: int = 1280)` (frozen dataclass) with `to_json() -> {"widthPx", "heightPx", "deviceScale", "imageMaxSize"}`; `InspectionResult.capture: CaptureInfo | None = None`; `VideoSource.size -> tuple[int, int]` (native width, height).
- Consumes: nothing from other tasks.

- [ ] **Step 1: Add the `wide` clip** to `build_all` in `tests/fixtures.py`: `testsrc2=size=1600x900:rate=10`, 1 s, `libx264`, `yuv420p`, key `"wide"`, file `wide.mov`. It is larger than 1280, so its keyframes are reduced.
- [ ] **Step 2: Write the failing tests** in `tests/test_inspect_golden.py`:
  - `test_video_result_carries_the_native_size`: `inspect_video(clips["wide"], output_dir=tmp_path).to_json()["capture"] == {"widthPx": 1600, "heightPx": 900, "deviceScale": None, "imageMaxSize": 1280}`, and the first keyframe PNG is 1280x720 (read the IHDR bytes 16-24).
  - `test_image_result_carries_the_native_size`: `inspect_image(clips["image"], ...)` gives `capture == {"widthPx": 160, "heightPx": 90, "deviceScale": None, "imageMaxSize": 1280}`.
  - `test_small_video_is_not_reduced`: for `motion.mov` the capture is 160x90 and the keyframe PNG is 160x90 too.
  In `tests/test_source.py`: `test_size_is_the_native_frame_size` (`VideoSource(clips["wide"]).size == (1600, 900)`).
- [ ] **Step 3: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_inspect_golden.py tests/test_source.py -q -k "native_size or not_reduced"`
  Expected: FAIL (`KeyError: 'capture'` and `AttributeError: ... 'size'`).
- [ ] **Step 4: Implement** `VideoSource.size` from `self._stream.codec_context.width/height`; `CaptureInfo` and the optional `capture` field plus its `to_json` entry (key present only when set); `inspect_video` sets `CaptureInfo(*source.size)`; `inspect_image` sets it from the decoded frame's `width` and `height`. The `1280` limit is one constant shared by `png_at`'s default and `CaptureInfo.image_max_size`.
- [ ] **Step 5: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS. The golden files are not edited: `assert_matches_golden` compares named keys only, and the new tests cover `capture`. Record that in the ledger as a ruling.
- [ ] **Step 6: Commit**
  ```bash
  git add src/anypoach/analysis/types.py src/anypoach/analysis/source.py src/anypoach/analysis/inspect.py tests/fixtures.py tests/test_inspect_golden.py tests/test_source.py
  git commit -m "feat(analysis): report the native size of the capture"
  ```

### Task 2: Device scale from the window into the brief

**Files:**
- Modify: `src/anypoach/ui/controller.py` (`choose_region(region, device_scale=None)`, `device_scale` property, `stop()` copies it into the result)
- Modify: `src/anypoach/brief/store.py` (`share` writes `evidence.capture` from the result; no change if `to_json` already carries it)
- Modify: `src/anypoach/ui/app.py` (`_choose` remembers the screen's `devicePixelRatio()` for non-preview backends, `None` for the portal; `_chosen` passes it)
- Test: `tests/test_ui_controller.py`, `tests/test_ui_window.py`, `tests/test_brief_store.py`

**Interfaces:**
- Consumes: `CaptureInfo` and `InspectionResult.capture` from Task 1.
- Produces: `Controller.choose_region(region: Rect, device_scale: float | None = None) -> None`; `Controller.device_scale -> float | None`. After `stop()`, `result.capture.device_scale` equals the value given.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_ui_controller.py::test_device_scale_reaches_the_shared_brief`: record a short clip with the existing fake backend, `choose_region(rect, device_scale=2.0)`, `stop()`, `share()`, then `read_brief(...)["evidence"]["capture"]["deviceScale"] == 2.0` and `widthPx` equals the recorded width.
  - `::test_device_scale_is_null_when_not_given`: same without the argument, `deviceScale is None`.
  - `::test_choosing_again_resets_the_scale`: `choose_region(rect, 2.0)` then `choose_region(rect)` gives `device_scale is None`.
  - `tests/test_ui_window.py::test_the_overlay_screen_scale_is_passed_to_the_controller`: with the offscreen platform (ratio 1.0) and a non-preview backend, after the window's `_chosen(Rect(...))`, `window.controller.device_scale == 1.0`; with a preview backend it is `None`.
  - `tests/test_brief_store.py::test_share_keeps_capture_in_the_evidence`: a result with `capture=CaptureInfo(1854, 962, None)` shares to `evidence["capture"] == {"widthPx": 1854, "heightPx": 962, "deviceScale": None, "imageMaxSize": 1280}`.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_controller.py tests/test_ui_window.py tests/test_brief_store.py -q -k "scale or capture"`
  Expected: FAIL (`TypeError: choose_region() takes 2 positional arguments` and `KeyError`).
- [ ] **Step 3: Implement** the controller argument and property (cleared by `choose_region` when absent and by `close()`); in `stop()` replace the result's `capture` with the same width and height and the stored `device_scale` (`dataclasses.replace`, the way `pointer_trace` is set today); in `app.py` keep `self._device_scale` set in `_choose` (`overlay_screen.devicePixelRatio()` for `SelectionOverlay`, `None` for `FrozenSelection`) and pass it in `_chosen`.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/ui/controller.py src/anypoach/ui/app.py src/anypoach/brief/store.py tests/test_ui_controller.py tests/test_ui_window.py tests/test_brief_store.py
  git commit -m "feat(ui): pass the screen scale into the brief"
  ```

### Task 3: Size captions on every returned image

**Files:**
- Modify: `src/anypoach/mcp/server.py` (`png_size`, `size_note`, used by `_keyframe`, `_drag_release_content` and `anypoach_read_moment`)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `evidence.capture` as written by Task 2 (`widthPx`, `heightPx`, `deviceScale`).
- Produces: `size_note(png: bytes, capture: dict | None) -> str`, returning `"1280x664, reduced from 1854x962 (x0.69)"` when the image is smaller than the native size, `"1854x962, native size"` when equal, and `""` when `capture` is absent or malformed (callers then add nothing). The note is appended to the existing text line before the image, for example `peak at 10786 ms (1280x664, reduced from 1854x962 (x0.69))`.

- [ ] **Step 1: Write the failing tests** in `tests/test_mcp_server.py`, reusing `base_brief`/`write_active`:
  - `test_keyframe_caption_states_the_native_size`: add `evidence["capture"] = {"widthPx": 1854, "heightPx": 962, "deviceScale": None, "imageMaxSize": 1280}` to the brief, make the reference PNG 1280x664, call `anypoach_read_brief`; the text before the image contains `1280x664, reduced from 1854x962 (x0.69)`.
  - `test_odd_native_size_is_exact`: native 1853x961 and a 1280x664 image gives `reduced from 1853x961 (x0.69)`.
  - `test_native_size_image_says_so`: a 160x90 image with native 160x90 gives `160x90, native size`.
  - `test_brief_without_capture_gets_no_scale_note`: the existing brief with no `capture` returns the same text as before (`start at 0 ms`) and no error.
  - `test_read_moment_caption_states_the_scale`: `anypoach_read_moment` on a video whose `capture` is larger than the returned PNG carries the note in its first text.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_mcp_server.py -q -k "caption or native or scale_note"`
  Expected: FAIL (the captions are absent).
- [ ] **Step 3: Implement** `png_size(data)` by reading the IHDR width and height (bytes 16 to 24, `struct.unpack(">II", ...)`), and `size_note` per the Interfaces block (scale `= image width / native width`, formatted with two decimals; invalid `capture` values return `""`). Use the note in `_keyframe`, in the drag-release frame lines, and in `anypoach_read_moment`'s first text. Pass `capture` down from the validated brief; do not validate more than `isinstance(..., int)` and positive.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/mcp/server.py tests/test_mcp_server.py
  git commit -m "feat(mcp): caption images with their real size and scale"
  ```

### Task 4: `maxSize` and `crop` on `anypoach_read_moment`

**Files:**
- Modify: `src/anypoach/analysis/source.py` (`VideoSource.png_at(seek, max_size=1280, crop=None)`)
- Modify: `src/anypoach/analysis/inspect.py` (`read_video_moment(path, time_ms, *, max_size=1280, crop=None) -> bytes`)
- Modify: `src/anypoach/mcp/server.py` (`Crop` model, two new parameters, caption for crops)
- Test: `tests/test_source.py`, `tests/test_inspect_golden.py`, `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `size_note` from Task 3 (extended with an optional `crop` argument that prefixes `crop x,y WxH of NWxNH, `).
- Produces: `crop` is `(x, y, width, height)` in native pixels, a tuple of ints for `png_at`/`read_video_moment`, and `Crop(x: int ge 0, y: int ge 0, width: int ge 1, height: int ge 1)` on the MCP side. The crop is applied to the native frame before any reduction. Errors are `ValueError` with the messages `"Crop must fit inside the {W}x{H} frame"` and `"Reference image exceeds the 5 MB limit; use a smaller crop or maxSize"`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_source.py::test_png_at_crops_native_pixels_before_reducing`: on `wide.mov`, `png_at(seek, max_size=1280, crop=(100, 50, 400, 300))` is a 400x300 PNG whose pixels equal the same rectangle of the native frame (compare against `frame.to_ndarray(format="rgb24")[50:350, 100:500]` with a tolerance of 1).
  - `::test_png_at_reduces_a_crop_that_exceeds_max_size`: crop 1000x800 with `max_size=500` gives a PNG no larger than 500 on its longest side, aspect kept.
  - `::test_png_at_rejects_a_crop_outside_the_frame`: crops `(1500, 0, 200, 100)`, `(0, 0, 0, 10)`, `(-1, 0, 10, 10)` all raise `ValueError` matching `Crop must fit inside the 1600x900 frame`.
  - `tests/test_mcp_server.py::test_read_moment_crop_and_max_size`: through the stdio client, `anypoach_read_moment(timeMs=0, crop={"x":100,"y":50,"width":400,"height":300})` returns a 400x300 image and a text that contains `crop 100,50 400x300 of`; `maxSize=640` on the full frame returns an image 640 wide.
  - `::test_read_moment_reports_a_bad_crop`: an out-of-frame crop is an error result with the message above, not an exception, and `maxSize=8` (below the minimum) is rejected by validation.
  - `::test_read_moment_refuses_an_oversized_crop_result`: with `FIVE_MB` patched to a tiny value, the error message mentions "smaller crop".
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_source.py tests/test_mcp_server.py -q -k "crop or max_size"`
  Expected: FAIL (`TypeError: ... unexpected keyword argument 'crop'`).
- [ ] **Step 3: Implement** the crop by converting the frame to native RGB (`frame.reformat(format="rgb24").to_ndarray()`), slicing, wrapping the slice with `av.VideoFrame.from_ndarray(..., format="rgb24")` and handing it to `scaled_png`. Validate the rectangle against `frame.width`/`frame.height` first. In the server add `maxSize: Annotated[int, Field(ge=16, le=8192)] = 1280` and `crop: Crop | None = None`, pass them to `read_video_moment`, and build the caption with `size_note`. The 5 MB check keeps its place, with the new message.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/analysis/source.py src/anypoach/analysis/inspect.py src/anypoach/mcp/server.py tests/test_source.py tests/test_inspect_golden.py tests/test_mcp_server.py
  git commit -m "feat(mcp): read a moment at native scale with maxSize and crop"
  ```

### Task 5: Handoff prompt, docs and the performance baseline

**Files:**
- Modify: `src/anypoach/ui/controller.py` (`handoff_prompt`)
- Modify: `tests/test_ui_controller.py`
- Modify: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md` (the tool and brief contract changed), `docs/superpowers/baseline.md`
- Modify: `tools/bench.py` (accept an optional clip name so the large clip can be timed)

**Interfaces:**
- Consumes: the `capture` field and the caption format from Tasks 1 to 4.
- Produces: two sentences appended to `handoff_prompt`: measurements in images are capture pixels and may be reduced, so read the caption and ask when `capture.deviceScale` is null; and a value in `evidence.capture` divided by `deviceScale` gives CSS pixels.

- [ ] **Step 1: Write the failing test** in `tests/test_ui_controller.py`: `test_handoff_prompt_explains_size_and_scale` asserts the prompt contains `evidence.capture`, `deviceScale`, and "reduced" (the sentence also tells the assistant to ask when `deviceScale` is null). The existing prompt tests keep passing unchanged.
- [ ] **Step 2: Run to verify it fails**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_ui_controller.py -q -k explains_size`
  Expected: FAIL.
- [ ] **Step 3: Implement** the prompt change. Run the suite.
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q` Expected: PASS.
- [ ] **Step 4: Commit the code**
  ```bash
  git add src/anypoach/ui/controller.py tests/test_ui_controller.py
  git commit -m "feat(ui): explain capture size and scale in the handoff prompt"
  ```
- [ ] **Step 5: Docs.** README: the new `capture` field, the captions, `maxSize` and `crop`, and what "deviceScale null" means on Wayland. CONTRIBUTING and CLAUDE.md: the new fields in the brief and tool contract. Any mention of the original Poach follows the AGENTS.md rule (docs only, warm mockery; for example, it also shrinks to 1280 px without saying so).
- [ ] **Step 6: Baseline.** Make a 1920x1080, 30 s clip (`ffmpeg -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 30 -c:v libx264 -pix_fmt yuv420p big.mov`), extend `tools/bench.py` with an optional clip argument, run it, and add the wall time, CPU and peak RSS to the Python section of `docs/superpowers/baseline.md`. Also note one live Wayland recording's `gst-launch` and Python CPU; that step needs the user's manual run, so mark it pending if not done. A slow step that a profile ties to our own Python (not PyAV, numpy or libx264) is a finding to ledger and report, not something to rewrite here.
- [ ] **Step 7: Verify and commit the docs**
  Run: `uv run ruff check src tests tools && QT_QPA_PLATFORM=offscreen uv run pytest -q`
  Expected: clean, all pass.
  ```bash
  git add README.md CONTRIBUTING.md CLAUDE.md docs/superpowers/baseline.md tools/bench.py
  git commit -m "docs(fidelity): document capture size, scale and crop"
  ```

## Self-Review

- **Spec coverage (Design A):** `evidence.capture` (Tasks 1, 2), captions (Task 3), `maxSize` and `crop` (Task 4), prompt (Task 5), compatibility with old briefs (Task 3, test), goldens (Task 1, ruling: not edited). The Go question's measurement is Task 5, Step 6.
- **Types:** `CaptureInfo` and the `capture` JSON keys (`widthPx`, `heightPx`, `deviceScale`, `imageMaxSize`) are the same in Tasks 1 to 3; `crop` is `(x, y, width, height)` everywhere.
- **Not here:** the Chrome extension (v0.2), motion segments and phase 2b (v0.3), macOS pointer and permission hint (v0.2). The tag and the GitHub pre-release happen after PR #2 merges, with the user's go-ahead.
