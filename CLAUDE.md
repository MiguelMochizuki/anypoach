# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` holds the repository rules (package boundaries, privacy of captures, Conventional Commits, README/CONTRIBUTING upkeep). Read it first; this file only adds commands and architecture.

## Commands

pnpm workspace + Turborepo (Node >=20.19, pnpm 11).

```sh
pnpm build                                   # turbo: tsc for packages/core, then packages/mcp-server
pnpm exec turbo run typecheck                # tsc --noEmit in both packages
pnpm --filter @poach/core test               # builds, then node --test test/*.test.mjs
pnpm --filter @poach/mcp-server test         # builds core + server, then node --test
node --test packages/core/test/recording.test.mjs   # single test file (needs a prior build)
node --test --test-name-pattern="<name>" packages/mcp-server/test/handoff.test.mjs   # single test

swift build --package-path apps/macos        # macOS app (macOS only)
bash scripts/test-pointer-trace-buffer.sh    # Swift tests: plain swiftc + executable, no XCTest
bash scripts/test-font-matcher.sh
pnpm build:connectors                        # build + esbuild-bundle the MCP server into outputs/connectors (Codex marketplace + Poach.mcpb)
bash scripts/build-macos-app.sh              # full outputs/Poach.app (bundles node/ffmpeg runtime, codesigns)
bash scripts/package-beta.sh                 # release zips + SHA256SUMS in outputs/beta
```

Tests are `.mjs` files that import the built `dist/`, so always build before running them directly. There is no linter. The Swift tests compile only the specific source files they cover (see the scripts), so new Swift code under test must stay free of dependencies on the rest of the app.

### Python rewrite (`python/`, in progress)

```sh
cd python && uv sync --group dev
uv run pytest                                  # fixtures need the ffmpeg CLI; skips TS-server parity tests if packages/mcp-server/dist is missing
uv run pytest tests/test_inspect_golden.py -k motion
uv run ruff check src tests tools
uv run poach-mcp                               # stdio MCP server
uv run poach                                   # minimal capture window (needs `uv sync --extra ui`; tests use QT_QPA_PLATFORM=offscreen)
```

Cross-platform replacement for the analysis core, brief storage and MCP server, and the only code that is meant to run off macOS. PyAV and numpy decode in one process (no ffmpeg children). Screen capture (`mss` + PyAV) and a minimal PySide6 window (`uv run poach`) exist but are only unit-tested here (no Windows or X11 desktop); `pytest -m live` needs a real display. `packages/core` is the oracle: `python/tests/golden` is generated from it with `python/tools/make_goldens.mjs`. The design is `docs/superpowers/specs/2026-11-20-poach-portable-rewrite-design.md`, the plan `docs/superpowers/plans/2026-11-20-poach-portable-phase1.md`, and measured timings are in `docs/superpowers/baseline.md`.

## Architecture

Three pieces connected by files on disk, not by network (plus the unpacked Chrome extension in `apps/chrome`, which POSTs element evidence to the app's local HTTP bridge on `127.0.0.1:47831`):

1. **`apps/macos`** (SwiftUI, ScreenCaptureKit; a single `PoachApp` executable target). `Sources/Capture` records and samples the pointer (`PointerTraceBuffer`, 120 Hz, capped at 5,000 events). `Sources/App/PoachInspectionRunner.swift` shells out to `node` to run `packages/core` (bundled at `Resources/core/dist/index.js` inside the app) and decodes the result into `PoachInspection`. `PoachHandoff.swift` writes the shared brief.
2. **`packages/core`** (headless TS, no AppKit): `extractor.ts` drives `ffmpeg`/`ffprobe` as external binaries to produce keyframes, palette (`palette.ts`) and motion timing (`motion.ts`) for videos and images. Public surface is only `src/index.ts`.
3. **`packages/mcp-server`** (stdio MCP, `poach_read_brief`, `poach_read_moment`, ...): reads the brief the app wrote and calls `@poach/core` to serve frames and derive click/drag candidates from the pointer samples.

The handoff contract between app and MCP server is `~/Library/Caches/Poach/active-brief.json` (latest) plus `briefs/<uuid>.json` (per share), user-only permissions, 24 h expiry. Changing the brief shape means updating both `PoachHandoff.swift` and the MCP server, and keeping the omitted-ID "latest" behavior. Details are in CONTRIBUTING.md ("Capture and handoff checks").

**Packaging.** `build-macos-app.sh` runs `build-connectors.mjs`, which esbuild-bundles `packages/mcp-server/dist/index.js` into a single `server.mjs` for the Codex marketplace plugin and the Claude `.mcpb`. In an installed app, `scripts/launch-connector.sh` runs that `server.mjs` with the app's bundled `runtime/bin/{node,ffmpeg,ffprobe}`, so the server and core must work with only those binaries on `PATH`. Build output lives in `outputs/` (gitignored), and `.github/workflows/beta-smoke.yml` is a manual macOS smoke test of a released beta, not a CI build or test run.

## Gotchas

- MCP stdout is the protocol channel. Never `console.log` in `packages/mcp-server` or anything it imports; use stderr.
- Screen capture needs macOS Screen Recording permission, so it can't be exercised in headless or Linux environments. The `SCRecordingOutput` path needs macOS 15, while inspecting existing files must keep working on macOS 14.
- The `scripts/*.sh` Swift tests and the app build need a Mac. TypeScript build, typecheck and tests work anywhere with Node and ffmpeg.
