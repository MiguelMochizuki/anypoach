# Using the window

`uv run anypoach` (or `anypoach` from the zip) opens the window. This guide covers everything it does. The short version is in the [README](../README.md#record-and-hand-off).

## Record

Choose what to capture:

- **Area:** drag a rectangle on the screen.
- **Full screen:** the whole screen.
- **Window:** one window. A list of windows on Windows, X11 and macOS; the portal's own window picker on Wayland. The recording does not follow the window if it moves.
- **Screenshot:** a still of the chosen area.
- **Import…:** analyze a video (`.mp4`, `.mov`) or an image from disk.

Then record (up to 30 s) and stop. While an area is recorded, a thin red frame marks it from the outside, so it is not in the video (not shown on Wayland, where no overlay can be placed). Outside Windows the window hides while recording and a tray menu stops it.

## Review

The review panel plays the recording frame by frame: **Space** plays and pauses, **Left** and **Right** step one frame. Bands on the timeline show where the video moves. You can:

- pin a comment to any moment (up to 50, 500 characters each);
- write general instructions for the whole capture.

Comments and instructions travel in the brief as `evidence.annotations` and `context`, and the assistant sees each comment next to the frame it is pinned to. The frames are decoded once, kept in memory, and dropped when you record again or close the window. Copy the prompt when you are done; it does not wait for the frames. **Enter** activates the focused button.

## Palette

Under the keyframes, the palette strip lets you change a color (click it), drop one (**×**), add one (up to 12) or reset to the analyzed palette. The brief carries your version.

## Favorites

- **Save as favorite…** keeps the handoff: instructions, notes, palette, timing, pointer evidence and up to three reference images, but not the video.
- **Favorites…** copies a fresh prompt from one, and exports or imports `.anypoach` files to share them.
- Favorites are the only thing AnyPoach keeps until you delete it, in a private folder (`ANYPOACH_DATA_DIR` overrides it). A handoff made from a favorite has no `anypoach_read_moment`.

## Match font

On a screenshot or an imported image, **Match font…** lets you drag over one line of text, type what it says, and ranks the fonts installed on your computer by how their letters look. The one you choose goes into the handoff as `visualFontMatch`. It is an approximation: there is no text recognition.

## Continue with an assistant

**Continue with Claude** and **Continue with Codex** copy the prompt and try to open that assistant's desktop app (`claude://`, `codex://`; these schemes are unverified). If the app cannot be opened, the prompt is still on the clipboard.

## Tray and global shortcut

- Where the desktop has a tray, its icon records the full screen without opening the window. Its menu can also choose an area, record it, or take a screenshot of it.
- **Settings… > Global shortcut** (off until you turn it on; Windows and X11 only) makes **Ctrl+Alt+Shift+P** start a full-screen recording and stop it. It registers that one chord with the system and sees no other key press.

## Settings

**Settings…** shows how much space AnyPoach uses and clears unused captures (never what a valid brief or the open window needs), copies the connect command for Claude Code, Codex or any client, checks for updates on request, and reopens the welcome tour. On first launch the tour explains the flow, names the one thing your system asks for before recording works, and offers to pair the Chrome companion.

## Platform notes

- **macOS:** the first recording triggers the system Screen Recording prompt. Allow AnyPoach (or the terminal that runs it) in System Settings > Privacy & Security > Screen Recording, then quit and reopen it. Without that permission, window names show only the app's name.
- **Wayland:** the screen comes through the desktop portal, which asks you to confirm each recording, and needs GStreamer with its PipeWire plugin (Debian and Ubuntu: `sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-pipewire`). AnyPoach tells you what is missing. The compositor draws the cursor into the video, and the pointer trace stays off.
- **Windows and X11:** the pointer trace is sampled from the system at 120 Hz.
