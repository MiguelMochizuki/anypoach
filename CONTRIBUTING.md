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

Set `POACH_CODESIGN_IDENTITY` to an installed code-signing identity to preserve the app's signing identity across builds. The default ad-hoc signature can require renewed Screen Recording approval after each rebuild. Developer ID builds enable the hardened runtime and request a secure timestamp. GitHub binary distribution additionally requires a notarization and dependency-packaging step; the development bundle currently references this checkout and its Node.js installation.

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
