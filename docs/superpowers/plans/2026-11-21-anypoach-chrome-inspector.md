# Chrome Page Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hovering any element shows a live inspector card on the page; pinning a component adds its measured descendants to the brief; the parity document becomes a release roadmap.

**Architecture:** `capture.js` gains a card (closed shadow DOM, models and placement as pure functions) and `measureComponents(root)`, which feeds two optional lists, `components` and `componentsAtEnd`, into the existing session. The loopback server validates the lists, `bridge.js` drops `componentsAtEnd` when a session is over the limit, and the MCP summarizes them. Nothing new is sent before a component is pinned.

**Tech Stack:** Python 3.11 + pydantic (server, MCP), plain JavaScript MV3 (extension), Node and headless Chrome for the extension tests, `uv`, `ruff`.

**Spec:** `docs/superpowers/specs/2026-11-21-chrome-inspector-design.md`. Branch `MiguelMochizuki/chrome-inspector`, cut from `MiguelMochizuki/chrome-companion` (PR #3, still open): rebase onto `main` once PR #3 merges.

## Global Constraints

- Component lists: at most **40** per list, depth at most **6**, `text` at most **80** characters, `rect` relative to the root's top-left corner, rounded to 0.1.
- Selection when there are more than 40 visible descendants: keep the largest by area (rect clipped to the root's rect), own text breaks ties; output stays in document order; `parent` is the index of the nearest kept ancestor, or `-1` for a direct child of the root.
- Same exclusions as `visibleText()`: `input, textarea, select, [contenteditable], [hidden], [aria-hidden=true], script, style`; skip zero-size, `visibility` not visible, and `checkVisibility` false.
- The card shows measurements only, never element text, and exists only in the `selecting` phase; after pinning, no `[data-anypoach-inspector]` element remains in the page.
- Contract: `components` and `componentsAtEnd` are optional; sessions without them stay valid; the models keep `extra="ignore"` like every other model in `bridge/evidence.py` (ruling: the spec's "unknown field is refused" becomes "unknown fields are ignored", the behavior the rest of the contract already has).
- The loopback listener, the 256 KiB body limit, the pairing code and the privacy rule in `AGENTS.md` do not change.
- Card colors: background `#FAFAF8`, outline `#D8D8D3`, ink `#292927`, highlight cobalt `#2025C8`, 14 px corners, dark full-width button style from the Poach editor; English UI text like the rest of the extension.
- Commit subjects are `type(scope): summary`, staged by file name, no AI attribution lines (repo is AI-driven, `ai.policy=driven`).
- The original Poach is named only in docs and in the one-line license notice already present in adapted files; never in code or tests.

## Review Focus

- A root with more than 40 visible descendants, deeply nested: the largest are kept, order and `parent` stay coherent (Task 2).
- Hidden, `aria-hidden`, zero-size and form-field descendants, and a root detached while measuring: never reach the list; a detached root gives `[]` (Task 2).
- A session over 256 KiB because of `componentsAtEnd`: the extension drops that list and still sends; a session that is over for any other reason still fails with the existing message (Task 2).
- Transparent or translucent colors on the card (`rgba(0, 0, 0, 0)`): shown as "transparent" or an 8-digit hex, never an empty or wrong hex; a target at the viewport edge: the card stays fully inside the viewport (Task 3).
- Sessions from the previous extension version (no component fields) and malformed lists (41 items, ids out of order, `parent` not before `id`): the first is accepted, the second is refused with 422 (Task 1).

---

### Task 1: Validate `components` and `componentsAtEnd`

**Files:**
- Modify: `src/anypoach/bridge/evidence.py` (new `_Component`, two optional `_Session` fields, a validator)
- Test: `tests/test_bridge_evidence.py`, `tests/test_bridge_server.py`

**Interfaces:**
- Consumes: `_Model`, `_Element` and `parse_evidence()` in `bridge/evidence.py`.
- Produces: `parse_evidence()` keeps `components` and `componentsAtEnd` (lists of `{"id": int, "parent": int, "target": {tag, role, classes}, "rect": [x, y, w, h], "styles": {name: str}, "text": str}`) when present and valid; absent fields stay absent. Task 4 reads them from the stored brief.

- [ ] **Step 1: Write the failing tests** in `tests/test_bridge_evidence.py`, with a helper `component(i, parent=-1)` returning a valid item with `id=i`:
  `test_components_round_trip_and_stay_optional` (a session with both lists of 3 items comes back unchanged; `session()` without them has no such keys); `test_forty_components_are_accepted_and_forty_one_refused` (`ValueError` for 41); `test_component_ids_must_follow_the_list_and_parents_come_first` (ids `[0, 2]` refused; `parent == id` refused; `parent = -1` and `parent < id` accepted; `parent = -2` refused); `test_component_text_is_limited_to_80_characters` (81 refused); `test_a_realistic_session_with_both_lists_fits_the_body_limit` (40 components with 17 styles of about 25 characters each, twice, plus 48 states and 16 animations from the existing helpers, serialized with `json.dumps` is under `BYTE_LIMIT`). In `tests/test_bridge_server.py`: `test_a_session_with_41_components_is_422_and_one_with_components_is_204`.
- [ ] **Step 2: Run to verify they fail**
  Run: `uv run pytest tests/test_bridge_evidence.py tests/test_bridge_server.py -q -k "component"`
  Expected: FAIL (the fields are dropped as extras, so the round trip and the 41-item refusal fail).
- [ ] **Step 3: Implement** `_Component(_Model)` with `id: int = Field(ge=0)`, `parent: int = Field(ge=-1)`, `target: _Element`, `rect: list[float]` (length 4), `styles: dict[str, str]`, `text: str = Field(max_length=80)`; add `components` and `componentsAtEnd` to `_Session` as `list[_Component] | None = Field(default=None, max_length=40)`; add a `model_validator(mode="after")` that, for each non-None list, requires `[c.id for c in list] == list(range(len(list)))` and `c.parent < c.id`.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
  Expected: PASS, clean.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/bridge/evidence.py tests/test_bridge_evidence.py tests/test_bridge_server.py
  git commit -m "feat(bridge): validate the component lists of a Chrome session"
  ```

### Task 2: Measure the descendants and survive oversized sessions

**Files:**
- Modify: `src/anypoach/chrome_extension/capture.js` (`measureComponents`, `start()`, `finish()`, `snapshot()`), `src/anypoach/chrome_extension/bridge.js` (size fallback)
- Create: `tests/chrome/components_page.html`
- Modify: `tests/chrome/bridge_flow.mjs`, `tests/test_chrome_extension.py`

**Interfaces:**
- Consumes: `styles()`, `rect()`, `describe()`, `styleNames` and the exclusion selector already in `capture.js`; the schema from Task 1.
- Produces: top-level (inside the IIFE) `function measureComponents(root) { ... }` returning the `Component[]` of Task 1 (rects relative to `root`); `recording.components` set in `start()` and sent in every snapshot; `componentsAtEnd` set only in `finish()`; in `bridge.js`, when the serialized body exceeds 256 KiB and `evidence.componentsAtEnd` exists, it is deleted once and the size is checked again before failing.

- [ ] **Step 1: Write the failing tests.** In `tests/test_chrome_extension.py`, extract the existing page-serving code into a helper `run_capture_page(tmp_path, name)` that returns the parsed `#out` payload, and add a `__anypoachTest` hook exporting `{ start, measureComponents }`. `tests/chrome/components_page.html`: a root `section` with a heading, a paragraph, three cards (each with a title and two tags), plus an `input`, a `[hidden]` div, an `aria-hidden` div and a zero-size div; with `#many` in the URL it instead builds 60 children of different sizes, nested up to depth 8; the page calls `start(root)`, waits, then finishes through the listener like `capture_page.html` and writes `{evidence, components}` where `components = measureComponents(root)`. Tests: `test_components_are_measured_relative_to_the_root` (heading present with its font size, a card at the expected rect, `parent` indexes coherent, no input, hidden, aria-hidden or zero-size entry, every text at most 80 characters, `evidence.components` equals the measured list, `evidence.componentsAtEnd` present); `test_more_than_forty_descendants_keep_the_largest_in_document_order` (40 items, ids `0..39`, depth at most 6, the largest child present, document order kept); `test_a_detached_root_measures_nothing`. In `tests/chrome/bridge_flow.mjs` add `out.droppedComponentsAtEnd` (a session whose only excess is a 300 KiB `componentsAtEnd` returns `{ok: true}`) and keep `out.oversized` as an error; `test_bridge_flow_against_the_real_server` asserts both and that the stored session has no `componentsAtEnd`.
- [ ] **Step 2: Run to verify they fail**
  Run: `uv run pytest tests/test_chrome_extension.py -q`
  Expected: FAIL (`measureComponents` is not defined; the oversized session is refused).
- [ ] **Step 3: Implement `measureComponents(root: Element): Component[]`** in `capture.js`: walk the descendants to depth 6, filter by the Global Constraints, build the items, apply the largest-40 rule when needed and recompute `parent` as the nearest kept ancestor; own text is the concatenation of the element's direct text nodes, trimmed to 80. Call it in `start()` (store as `recording.components`), include `components` in `snapshot()`, and in `finish()` set `componentsAtEnd = measureComponents(root)` after the final `sample()` when the root is still connected. In `bridge.js` `handle()`, after computing `body`, if it is over the limit and `message.evidence.componentsAtEnd` exists, rebuild `body` without that key once.
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
  Expected: PASS, clean (Chrome and Node tests skip only when the tool is missing).
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/chrome_extension/capture.js src/anypoach/chrome_extension/bridge.js tests/chrome/components_page.html tests/chrome/bridge_flow.mjs tests/test_chrome_extension.py
  git commit -m "feat(chrome): measure the descendants of the pinned component"
  ```

### Task 3: The inspector card

**Files:**
- Modify: `src/anypoach/chrome_extension/capture.js` (card, `cardModel`, `placeCard`, `select()`, `endSelection()`)
- Create: `tests/chrome/inspector_page.html`
- Modify: `tests/test_chrome_extension.py`

**Interfaces:**
- Consumes: `styles()`, `rect()`, `describe()`, `select()` and `endSelection()` in `capture.js`.
- Produces: inside the IIFE, `cardModel(element) -> {name: str, size: "474 × 360", font: "Inter · 24/28 · 500", colors: [{label: "Text"|"Background"|"Border", hex: "#RRGGBB" | "#RRGGBBAA" | null}], extras: [str], animations: [str]}` (`hex: null` means transparent; `extras` lists radius, opacity, transform and shadow only when not default; `animations` has one `"300ms cubic-bezier(...)"` entry per running animation); `placeCard(target, card, viewport) -> [left, top]` with all arguments as plain arrays (`[x, y, w, h]`, `[w, h]`, `[w, h]`); a `showCard(element)` and `hideCard()` pair that manage one host `<div data-anypoach-inspector>` holding a closed shadow root; `endSelection()` calls `hideCard()`; the test hook exports `{ cardModel, placeCard, showCard, endSelection, select }`.

- [ ] **Step 1: Write the failing tests.** `tests/chrome/inspector_page.html` builds a few elements (a div with `background: rgba(0,0,0,0)` and a 1 px dashed border, a heading with a known font, an element with a running Web Animation of 300 ms and `cubic-bezier(0.4, 0, 0.2, 1)`) and writes JSON with their `cardModel`s, several `placeCard` calls, the count of `[data-anypoach-inspector]` after `showCard`, and the count after `endSelection()`. Tests: `test_card_model_reports_measurements_and_never_the_text` (size, font string, `hex` of an opaque color, `null` for the transparent background, an 8-digit hex for a translucent one, the animation entry, and no key holding the element's text); `test_the_card_is_placed_inside_the_viewport` (`placeCard([1700, 10, 100, 50], [260, 200], [1854, 960])` puts it left of the target; a target at the bottom edge pushes it up; a viewport smaller than the card clamps to an 8 px margin; every result satisfies `0 <= left` and `left + 260 <= viewport width`); `test_one_card_exists_while_choosing_and_none_after` (1 host after `showCard`, 0 after `endSelection()`, and the host's shadow root is not reachable from the page: `host.shadowRoot === null`).
- [ ] **Step 2: Run to verify they fail**
  Run: `uv run pytest tests/test_chrome_extension.py -q -k "card or placed"`
  Expected: FAIL (functions not defined).
- [ ] **Step 3: Implement** `cardModel`, `placeCard` (prefer the right of the target with a 12 px gap, else the left, else below or above, then clamp to an 8 px margin), `showCard`/`hideCard`, and wire them into `select()`: call `showCard` from the existing `highlight()` so `pointermove`, `focusin` and `↑` update it, re-render on `requestAnimationFrame` while the element has running animations, and hide it on `endSelection()`; the existing banner stays when no element is under the pointer and its text becomes "Click or Enter to pin · ↑ parent · Esc cancel" inside the card. Render with the Global Constraints colors: name and size on top, font, color capsules (rounded swatch plus hex underneath, "transparent" for `null`), extras, animations, the hint as a dark full-width bar.
- [ ] **Step 4: Run to verify they pass, then the whole suite, then look at it once.**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
  Expected: PASS, clean. Then load the unpacked folder in Chrome, press "Choose a component" on a real page and check that the card follows the pointer, stays inside the window near the edges, and disappears after pinning (the headless tests cannot judge how it looks).
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/chrome_extension/capture.js tests/chrome/inspector_page.html tests/test_chrome_extension.py
  git commit -m "feat(chrome): show an inspector card while choosing a component"
  ```

### Task 4: Give the assistant the components

**Files:**
- Modify: `src/anypoach/mcp/server.py` (`anypoach_read_brief` adds a summary line), `src/anypoach/mcp/descriptions.py`, `src/anypoach/ui/controller.py` (`handoff_prompt`)
- Test: `tests/test_mcp_server.py`, `tests/test_ui_controller.py`

**Interfaces:**
- Consumes: `evidence.browserEvidence.components` and `componentsAtEnd` as stored by the controller; `_brief_json`, `anypoach_read_brief`, `handoff_prompt`.
- Produces: in `anypoach_read_brief`, one extra text content item `"Chrome components: N measured at pin time (M at the end) on <origin>; the full list is in evidence.browserEvidence.components."` placed after the JSON text, present only when `components` is a non-empty list; the structured response is unchanged (it already carries the lists); `handoff_prompt` mentions `evidence.browserEvidence.components` as the measured structure of the component; `anypoach_read_moment` is unchanged.

- [ ] **Step 1: Write the failing tests.** In `tests/test_mcp_server.py`: `test_read_brief_summarizes_the_chrome_components` (a brief with 3 components, 2 at the end and an origin returns that item with the right numbers and structured content equal to the stored lists), `test_read_brief_has_no_components_line_for_older_sessions`, and `test_read_moment_does_not_repeat_the_component_list`. In `tests/test_ui_controller.py`: extend `test_handoff_prompt_prefers_browser_evidence` so the prompt names `evidence.browserEvidence.components`.
- [ ] **Step 2: Run to verify they fail**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest tests/test_mcp_server.py tests/test_ui_controller.py -q -k "component or browser"`
  Expected: FAIL.
- [ ] **Step 3: Implement** the summary item (validated like the other Chrome fields: a malformed list yields no line instead of an error), the prompt sentence, and the two tool descriptions (mention that `read_brief` carries the descendants of the pinned component with size, font, colors and text, to use instead of measuring the video).
- [ ] **Step 4: Run to verify they pass, then the whole suite**
  Run: `QT_QPA_PLATFORM=offscreen uv run pytest -q && uv run ruff check src tests tools`
  Expected: PASS, clean.
- [ ] **Step 5: Commit**
  ```bash
  git add src/anypoach/mcp/server.py src/anypoach/mcp/descriptions.py src/anypoach/ui/controller.py tests/test_mcp_server.py tests/test_ui_controller.py
  git commit -m "feat(mcp): tell the assistant about the measured components"
  ```

### Task 5: Documentation, release roadmap and release hygiene

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/superpowers/poach-parity.md`
- Modify: `tests/test_chrome_extension.py`

**Interfaces:**
- Consumes: the behavior of Tasks 1 to 4, the existing "Chrome companion" subsection of the README, the "O que falta" and "Ordem proposta" parts of `poach-parity.md`, the manual check for the extension in CONTRIBUTING.
- Produces: a "Roteiro de releases" section in `docs/superpowers/poach-parity.md` and a "Releases" section in `CONTRIBUTING.md`; a test that keeps the extension's version equal to the package's.

- [ ] **Step 1: Write the failing test** `test_extension_version_matches_the_package` in `tests/test_chrome_extension.py`: `tomllib` reads `[project].version` from `pyproject.toml` and it equals the manifest's `version`.
- [ ] **Step 2: Run to verify it passes today, then break it on purpose:** change nothing yet; run it (it passes at `0.1.0` and `0.1.0`), then temporarily set the manifest to `9.9.9` and confirm it fails, and restore it. The test exists to guard the version bump of the next release.
- [ ] **Step 3: Write the docs.**
  - `poach-parity.md`: replace "Ordem proposta" with a **"Roteiro de releases"** table (version, content, state, where it lives), marked as a proposal until the user confirms it: `v0.1.0` pre-release, published (size and scale, Wayland capture); `v0.2.0` Chrome companion (PR #3) plus the page inspector (this plan), in progress; `v0.2.1` macOS (`CGEventSource` pointer, screen-recording permission hint), own plan, not started; `v0.3.0` motion segments plus phase 2b (editor with comments, global shortcut and tray, onboarding, window mode), not started; later and unscheduled: import video or image, screenshot, storage cleanup, Chrome side panel (option B of the inspector design) and in-window list (option C), PyInstaller distribution, `.mcpb` and Codex connectors, favorites and font matcher. Update the Chrome row of the table to say the inspector is covered by this plan. Docs may mock the original with the warm tone `AGENTS.md` asks for.
  - `README.md`: in the Chrome companion subsection describe hovering to inspect, pinning, and what `components` adds to the brief; keep the "no Web Store listing yet" status.
  - `CONTRIBUTING.md`: extend the Chrome manual check (hover shows the card, the card stays inside the window at the edges, pinning removes it, the brief has `components` with the expected sizes and fonts, `read_brief` shows the summary line) and add a **"Releases"** section: the checklist is bump `version` in `pyproject.toml` and in `src/anypoach/chrome_extension/manifest.json` (a test keeps them equal), refresh docs (README, CONTRIBUTING, `poach-parity.md`), CI green on the three systems, notes in the style of v0.1.0, pre-release flag until 1.0, and the tag and release are created only after the user says so.
  - `CLAUDE.md`: in the `anypoach.bridge` item add the two optional lists, the 40-item and depth limits, and that `bridge.js` drops `componentsAtEnd` when a session is over the body limit; add a gotcha that the card lives in a closed shadow DOM, so tests read `cardModel()` instead of the DOM.
- [ ] **Step 4: Verify the text against the code** (limits, names, port, button labels) and run `uv run ruff check src tests tools && QT_QPA_PLATFORM=offscreen uv run pytest -q`.
  Expected: clean, all pass.
- [ ] **Step 5: Commit**
  ```bash
  git add tests/test_chrome_extension.py
  git commit -m "test(chrome): keep the extension version equal to the package"
  git add README.md CONTRIBUTING.md CLAUDE.md docs/superpowers/poach-parity.md
  git commit -m "docs(chrome): document the inspector and lay out the release roadmap"
  ```

## Self-Review

- **Spec coverage:** card with live values and Poach look (Task 3); `components` measured at pin and at end, limits, exclusions, largest-40 rule (Task 2); contract and 422 cases (Task 1); size fallback (Task 2); MCP summary and prompt (Task 4); privacy rules (Global Constraints and Task 3's "no card after pinning"); docs (Task 5). Parity and release roadmap, requested after the spec, are in Task 5. Not here, as the spec says: side panel, in-window list, cross-origin iframes, Web Store.
- **Rulings already made in this plan:** unknown fields are ignored, not refused (the existing models use `extra="ignore"`); `parent` is the nearest kept ancestor; the card reads border color and style directly from computed style and does not add them to the brief; worst-case size can exceed 256 KiB (17 styles of 90 characters in 40 components twice), so the tested guarantee is the realistic case plus the `componentsAtEnd` fallback, and a session still over the limit fails with the existing message.
- **Types:** `Component`, `measureComponents`, `cardModel`, `placeCard`, `showCard`, `hideCard` and the session keys `components`/`componentsAtEnd` carry the same names in every task that uses them.
