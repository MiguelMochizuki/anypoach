<p align="center"><img src="apps/macos/Assets/PoachIcon.png" width="88" alt="Poach pouch icon"></p>
<h1 align="center">Poach</h1>
<p align="center">A lightweight Mac app for the UI you wish you’d made.</p>
<p align="center"><strong><a href="https://github.com/guilopeszw/poach/releases/download/v0.1.0-beta.4/Poach-arm64.zip">Download for Apple silicon</a></strong> · <a href="docs/media/poach-demo.mp4">Watch the demo</a></p>

<p align="center"><a href="docs/media/poach-editor.png"><img src="docs/media/poach-editor.png" width="550" alt="Poach reviewing a reading-list bookmark animation, with the clip, extracted colors, and instructions for the assistant."></a></p>

## What does Poach do?

Record how an interface responds to a click, hover, or drag. Add notes directly to the video timeline, then share the capture with Codex or Claude. Your assistant can inspect the frames you marked and use them to recreate the interaction in your project.

## From screen to chat

1. **Capture the interaction.** Record a screen area, a window, or a full display. Poach captures the pointer and leaves its own controls out of the video. Press **⌘⇧P** to select an area, then press it again to stop. You can also drop in an existing video or still image.
2. **Mark the details.** Pause the video and click the comment icon to leave a note at the playhead. Click a comment to return to its frame. Adjust the extracted palette and add any instructions that apply to the whole capture.
3. **Build with your assistant.** Choose **Copy handoff for chat** and paste it into your connected conversation. The MCP connector lets the assistant read your notes, see representative frames, and request a frame at a specific timestamp. Poach needs no separate AI API key.

In **Settings → Storage**, see how much space Poach uses and choose **Clear unused captures** to remove old recordings and extracted frames. Poach keeps the open edit, the active handoff, and your imported originals.

## Install on your Mac

Download the Apple silicon build above, unzip it, and move **Poach.app** to Applications. Choose the connector for your assistant, then open a new chat.

| Assistant | Install the MCP connector |
| --- | --- |
| [Codex installer](https://github.com/guilopeszw/poach/releases/download/v0.1.0-beta.4/Poach-Codex.zip) | Unzip and double-click **Install Codex.command**. |
| [Claude Desktop extension](https://github.com/guilopeszw/poach/releases/download/v0.1.0-beta.4/Poach.mcpb) | Open **Settings → Extensions → Advanced settings → Install Extension**. Select the downloaded file and enable Poach. |

**Beta requirements.** Screen recording requires macOS 15 or later. On macOS 14 you can import images and videos. Clips can be up to 30 seconds long. Poach records the screen without audio.

<details>
<summary>Download and first-launch help</summary>

Sign in to a GitHub account with access to the private beta. The app includes its runtime and video tools.

This beta is locally signed. If macOS blocks it, review **System Settings → Privacy & Security → Open Anyway**. To record, grant Poach access under **Screen & System Audio Recording** and reopen it if prompted.

Keep Poach in Applications so the connector can find it. If the handoff button is disabled, open a new chat with the connector enabled. For manual setup, open Poach’s **Settings** and choose **Copy Codex MCP** for the Terminal command or **Copy Claude MCP** for the Claude Desktop configuration.

</details>

<details>
<summary>What does my assistant receive?</summary>

Poach analyzes the media on your Mac. When your assistant reads a handoff, it receives your instructions, timestamped notes, palette, and requested frames. Motion timing and easing are estimates from sampled frames. A new handoff replaces the previous one, and each handoff expires after 24 hours.

</details>

[Contributing and local development](CONTRIBUTING.md) · [License](LICENSE)
