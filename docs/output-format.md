# What a recording produces

A recording produces a few keyframe PNGs and a **brief**: a JSON file with the analysis, the pointer trace, your notes and an instruction for the assistant. The assistant reads it through the MCP server.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `anypoach_read_brief` | Read the latest shared brief, or one by `briefId`: keyframes, palette, timing, pointer trace, notes. |
| `anypoach_read_moment` | Read one frame of the shared recording at a timestamp. `crop` (native pixels from the top left) and `maxSize` return a detail at native scale. |
| `anypoach_inspect` | Analyze a local `.mp4` or `.mov` file. |
| `anypoach_inspect_image` | Analyze a local still image. |

## Several interactions

When the recording holds several interactions, `evidence.segments` lists each one (up to 12) with its own start, peak, end, strength and timing. The 4 strongest come with start, peak and settled frames; the others are one `anypoach_read_moment` away. The top-level `keyframes` and `timing` stay those of the strongest one.

## Real size of the capture

`evidence.capture` records `widthPx`, `heightPx` and `deviceScale`. Keyframes are reduced to 1280 px, so every image the MCP returns is captioned with its real size (a 1854x962 recording arrives as 1280x664).

`deviceScale` is the number of video pixels per CSS pixel (the screen scale, adjusted when the recorder shrinks a capture past 1920 px) on Windows and X11, and `null` where it is unknown, such as Wayland or imported media. The prompt tells the assistant to ask instead of guessing.

## With the Chrome companion

The brief also holds `evidence.browserEvidence`: up to 48 states and 16 animations of the picked component, aligned to the video through `videoOffsetMs` and trimmed to the recording (one second of margin, plus the state that was in force when it began). See [Chrome companion](chrome-companion.md).

The repository ships no sample output.
