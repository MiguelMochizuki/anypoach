# Contributing to Poach

Thanks for helping improve Poach. The project is a pnpm/Turborepo monorepo with a native SwiftUI client, a TypeScript analysis core, and an MCP server.

## Development setup

Install Node.js 20.19 or newer, pnpm, Swift 6, and the `ffmpeg` and `ffprobe` command-line tools. On macOS, install FFmpeg with Homebrew:

```sh
brew install ffmpeg
```

Then install dependencies and build the TypeScript packages:

```sh
pnpm install
pnpm build
pnpm exec turbo run typecheck
```

Build the macOS package with:

```sh
swift build --package-path apps/macos
```

To build a Finder-openable app bundle, run `bash scripts/build-macos-app.sh`. It creates `outputs/Poach.app`, which is ignored by Git.

Set `POACH_CODESIGN_IDENTITY` to an installed code-signing identity to preserve the app's signing identity across builds. When installed, `Poach Local Development` is selected automatically and signed without a network timestamp. Otherwise the fallback ad-hoc signature can require renewed Screen Recording approval after each rebuild. Developer ID builds enable the hardened runtime and request a secure timestamp. GitHub binary distribution additionally requires a notarization and dependency-packaging step; the development bundle includes the analysis engine but still requires an external Node.js installation and FFmpeg tools.

## Project conventions

- Keep the analysis core deterministic, typed, headless, and independent from the macOS app.
- Keep MCP stdout reserved for protocol messages. Send diagnostics to stderr.
- Keep screen recordings local. Do not add network upload or telemetry without explicit product approval.
- Capture only what the person selected or explicitly started. Avoid recording microphone or system audio unless the product flow clearly requests it.
- Prefer system frameworks and existing command-line tools over adding runtime dependencies.
- Keep temporary media bounded and document any new retention behavior.
- Use clear, accessible labels and respect macOS appearance, contrast, and motion preferences.
- Add focused documentation when changing commands, permissions, supported file formats, or user data handling.

## Pull requests

1. Keep changes focused and explain the user-facing reason in the PR description.
2. Use one atomic commit per logical change, with a Conventional Commit message such as `feat(macos): record short screen clips` or `docs: explain local capture permissions`.
3. Include screenshots or a short recording when changing the macOS interface.
4. Run the TypeScript build and typecheck for TypeScript changes. Build the Swift package for macOS changes.
5. Describe any permissions added, data read or written, and platform limitations.
6. Do not commit generated `.build`, `dist`, `.turbo`, `node_modules`, or app bundle output.

By submitting a contribution, you agree that it is provided under the [Apache License 2.0](LICENSE). No separate contribution agreement is required.

The explicit MCP share action writes one replaceable snapshot under `~/Library/Caches/Poach/active-brief.json`. Keep this format compatible with `poach_read_brief`, preserve user-only permissions, and document changes to the 24-hour validity period. Expired snapshots are removed on read.

The review window uses AVKit for local video playback. Playhead notes are appended as timestamped text to the editable implementation context and included in the explicitly shared snapshot. Poach does not call an LLM API; the connected assistant interprets the capture evidence.

`poach_read_moment` only accesses the active explicitly shared video and enforces the same 24-hour validity period. It returns reference pixels directly, without retaining additional image files. Keep this scope when extending assistant inspection.

When validating automatic stop, let a native capture reach the full 30-second limit and verify the resulting clip with ffprobe. ScreenCaptureKit shutdown can add extra frames; the app uses `inspectRecording` to trim that overrun, while file imports use the strict `inspectVideo` limit. Confirm the returned source path points to the trimmed clip so playback and MCP moments use the same timeline.

Run `pnpm --filter @poach/core test` for the recording boundary regression. It requires FFmpeg/ffprobe, generates a synthetic 31.5-second clip, verifies normalization to 30 seconds and final-moment access, and checks that the import limit remains strict. Fixtures and extracted images are temporary and removed after the test.

Run `pnpm --filter @poach/mcp-server test` to verify assistant handoff through a real MCP stdio client. This test uses an isolated temporary HOME, synthetic video and brief; it checks notes, color instructions, images, timestamp bounds, and expiry without touching your active shared brief.

For capture diagnostics, use `log show --last 5m --style compact --predicate 'subsystem == "dev.poach.app" AND category == "CaptureLifecycle"'`. These macOS logs contain lifecycle milestones and numeric failure codes, not capture contents, notes, or source paths. A successful run reports selection requested, recording started, stop requested, file finalized, analysis completed, and review editor presented.

Shortcut validation: with Poach running, physically press Command–Shift–P from another app, verify selection opens, and cancel with Escape. Repeat during a recording to verify stop. Registration status is logged under subsystem `dev.poach.app`, category `HotKey`; status 0 confirms registration, not delivery. App-targeted synthetic keypresses are insufficient evidence of global shortcut delivery.

When checking assistant setup, verify the connector is available from the Settings tab and the review sheet. Verify Continue disables on disconnect and enables after initialization. Check both client tabs, copied shell quoting for paths with spaces, preserved existing Claude server entries, and the missing-server message. The native packaging script builds both TypeScript packages before embedding the local server path; the server and its dependencies remain in the checkout for development.

When checking video comments, post at two different times, close and reopen the sidebar, and select the earlier comment. Verify the player seeks to that moment and both timestamps appear in the copied prompt or shared brief.

Motion-analysis checks include stationary video. Verify that a quiet recording yields one resting frame, zero motion duration, and a null easing estimate in the assistant brief.

When changing the local dropzone benchmark, check the PNG success path, MP4 refusal, drag cancellation, and Replay in a browser. Use the server command in the README.
