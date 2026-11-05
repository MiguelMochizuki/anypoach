# Poach

Poach is a native macOS tool and local MCP server for turning short interface recordings into reusable motion context. It extracts representative keyframes, timing and easing estimates, and a compact color palette.

## What works today

- The macOS app records a selected portion, display, or window for up to 30 seconds with ScreenCaptureKit, including the mouse pointer and click indicators, then analyzes it locally and opens the opaque review editor.
- You can also load existing videos and still images from the app.
- The MCP server exposes `poach_inspect` for local video files.
- The MCP server exposes `poach_inspect_image` for local still images.
- The TypeScript core samples frames with the system `ffmpeg` and `ffprobe` executables. It writes small PNG keyframes and computes motion and palette summaries.

The first screen capture may ask for Screen Recording access. Grant it in **System Settings → Privacy & Security → Screen & System Audio Recording**, then reopen Poach if macOS requests it. Poach captures no audio and excludes its own windows. Captures and keyframes are stored under your temporary directory; nothing is uploaded.

The capture recorder uses ScreenCaptureKit's direct file output and requires macOS 15 or newer. On macOS 14, the app can still inspect existing recordings through the file picker or MCP server.

## Requirements

- macOS 14 or newer; macOS 15 or newer for direct screen recording
- Node.js 20.19 or newer and pnpm
- `ffmpeg` and `ffprobe` on `PATH`
- Swift 6 toolchain

## Build and open the macOS app

From the repository root:

```sh
pnpm install
pnpm build
bash scripts/build-macos-app.sh
open outputs/Poach.app
```

Poach opens a compact Capture tab at the edge of the screen and adds a pouch control to the menu bar. Choose a recording mode, or drop a video or image onto the import area. Clicking the import area opens a file picker. After inspection, the editor opens with playback, timestamped comments, colors, and instructions for your assistant.

The generated app bundle is written to `outputs/Poach.app`. Re-run the build script after changing the Swift sources.

Development builds automatically reuse an installed identity named `Poach Local Development`; otherwise they use ad-hoc signing. Rebuilding can invalidate the previous Screen Recording approval. If Poach is already enabled but macOS denies capture, remove the old entry in Screen & System Audio Recording, add the current app, then quit and reopen it.

For a stable signing identity, run `POACH_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" bash scripts/build-macos-app.sh`. The identity and private key must already be installed in your Keychain. GitHub binary releases should use Developer ID signing and Apple notarization; App Store publication is not required. This build command signs the bundle but does not notarize it. The analysis engine is bundled inside the app. Node.js, FFmpeg, and ffprobe are still external runtime requirements, so it is not yet a standalone redistributable release.

## Build the TypeScript packages

```sh
pnpm install
pnpm build
pnpm exec turbo run typecheck
```

The core currently limits input videos to 30 seconds and 512 MiB. Analysis defaults to 12 downscaled samples per second. Stationary captures produce a single resting frame and a zero motion duration. The timing field `bezier` is null when the sampled evidence cannot support an easing estimate. Keyframe PNGs are written to a temporary `poach-*` directory unless an output directory is supplied.

## Run the MCP server

Build first, then configure an MCP client to launch the server's compiled JavaScript. Example configuration:

```json
{
  "mcpServers": {
    "poach": {
      "command": "node",
      "args": ["/absolute/path/to/poach/packages/mcp-server/dist/index.js"],
      "env": {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

`poach_inspect` accepts an absolute `videoPath` and optional `outputDirectory`. It returns structured JSON with `keyframes`, `palette`, and `timing`. The MCP server only reads local video files and writes extracted PNGs; it does not upload recordings.

## Repository map

```text
apps/macos/          SwiftUI menu-bar app, capture service, and floating HUD
packages/core/       TypeScript frame extraction, motion analysis, and palette code
packages/mcp-server/ MCP server exposing poach_inspect
scripts/             Local packaging helpers
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and review expectations, and [AGENTS.md](AGENTS.md) for repository-specific guidance for coding agents. The project is licensed under Apache-2.0; see [LICENSE](LICENSE).

## Share a capture with an assistant

In the review window, click the speech bubble beside the video timeline. Playback pauses and the comments sidebar opens on the right. Write a comment and choose **Post comment**. Its text appears briefly above its marker. Click a marker or sidebar comment to return to that moment. Posted comments are included in the prompt and the shared brief in time order. Edit the palette or add implementation context, then choose **Continue with Codex or Claude**. Ask a connected assistant to call `poach_read_brief`. Share again after editing to replace the shared snapshot. **Copy Prompt** also works without MCP.

The shared snapshot is stored locally at `~/Library/Caches/Poach/active-brief.json` with user-only permissions. It contains context and inspection metadata, including local keyframe paths. It expires after 24 hours and is deleted when the MCP tool next reads an expired snapshot; it is not automatically deleted while Poach is idle. Sharing does not itself upload media, but your connected assistant can receive the returned data.

Palette swatches in the brief are editable. Color replacements and implementation context are included when copying or sharing; share again after edits. Each newly analyzed capture starts a fresh editor. The MCP tool includes up to three PNG keyframes by default (5 MB each maximum); pass `includeKeyframes: false` for metadata only. Missing keyframes are reported explicitly.

To register the local server with Codex after building, use `codex mcp add poach -- node /absolute/path/to/poach/packages/mcp-server/dist/index.js`. Reload the assistant connection if the tool is not yet visible. Ask it to call `poach_read_brief`, inspect the images, and implement the component in your current project.

A local development certificate is valid for development on the Mac where it is trusted. It is not a substitute for Developer ID signing and notarization of GitHub releases. Preserve its private key in Keychain across builds. Moving from an ad-hoc build to this certificate requires one fresh Screen Recording approval.

Assistants can call `poach_read_moment` with `timeMs` to inspect an exact moment from the currently shared video, including moments mentioned in your notes. It returns a reference PNG without saving another file. Timestamps must be before the clip ends; expired briefs and still-image briefs are rejected. This lets your chosen LLM interpret behavior without Poach requiring an API key.

Recordings that run slightly past 30 seconds while ScreenCaptureKit finishes stopping are trimmed to 30 seconds before analysis. The editor and shared brief use that trimmed video. The original and trimmed files remain in temporary storage; imported videos still enforce the 30-second limit without trimming.

Poach registers **Command–Shift–P** while running: it opens selected-area capture when idle and stops an active recording. The menu-bar panel reports if registration fails. The shortcut registers only that chord; it does not install a general keyboard monitor. Capture buttons remain available.

Open **Settings** to choose a window edge, a default recording mode, and a Codex or Claude Desktop configuration. Click **Copy** to copy the configuration. The review editor also opens Settings. **Continue with Codex or Claude** becomes available when an initialized Poach MCP client is running. If you updated from an older build, restart the assistant's MCP server so it can advertise its connection. To inspect local media, drop one image or video onto the Capture tab or click the drop zone to browse. Keep the project folder in place for this development configuration. Claude setup follows the [MCP local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

## Local dropzone benchmark

From the project root, run `python3 -m http.server 8741 --bind 127.0.0.1 --directory apps/benchmark` and open [the local benchmark](http://127.0.0.1:8741/). Record the drop zone and both sample files using Poach’s **Screen area** mode. Drag **mood.png** into the target to see progress, or **demo.mp4** to see the size-limit response. **Replay** resets the demo. Both files and the progress indicator are simulated locally.
