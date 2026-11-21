# Wayland portal spike

Measured on 2026-11-21 with `tools/portal_spike.py` on the development machine: GNOME on Wayland, portal
ScreenCast version 5, GStreamer 1.28.2 with PipeWire 1.6.2.

## What the portal returned

`Start` answers with one stream for a 1920x1080 monitor:

```
{'streams': ('a(ua{sv})', [(89, {'id': ('s', '0'), 'source_type': ('u', 1),
                                  'position': ('(ii)', (0, 0)), 'size': ('(ii)', (1920, 1080))})])}
```

Result values arrive as `(signature, value)` pairs, so `streams` is `results["streams"][1]` and each entry is
`(node_id, props)`. `OpenPipeWireRemote` returns a file descriptor.

## Reading the stream

`gst-launch-1.0 -q pipewiresrc fd=<fd> path=<node> always-copy=true ! videoconvert ! videoscale !
video/x-raw,format=BGRA,width=1920,height=1080 ! fdsink fd=1 sync=false`, started with `pass_fds=(fd,)`, works
and delivers frames of exactly `width * height * 4` bytes. The architecture of the plan holds.

| Mode | Frames in 10 s | Rate | `gst-launch` CPU |
| --- | --- | --- | --- |
| Embedded cursor (`cursor_mode=2`) | 142 | 14 fps | 7% of a core |
| Metadata cursor (`cursor_mode=4`) | 0 | none | 0% |

- The delivered frame size equals the portal `size` (1920x1080 on a 1x display). Fractional scaling was not tested.
- GNOME sends a frame when the screen changes, so a mostly still screen gives well under 30 fps. Capture must
  therefore repeat the newest frame between arrivals.
- With `cursor_mode=4` the pipeline received no video at all and logged no line that mentions the cursor, and
  `pipewiresrc` has no cursor property. The cursor position is not reachable from `gst-launch-1.0`.

## Verdict

- The cursor is embedded in the video (`cursor_mode=2`) and the Wayland pointer trace stays `available: false`.
  Reading the position would need `PyGObject` or a PipeWire binding, which the design excludes.
- Ruling for Task 5: `PortalBackend.grab` stamps each frame with the clock at the moment of the grab, not at the
  moment the frame arrived, so repeated frames get increasing times.
