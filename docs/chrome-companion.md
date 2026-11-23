# Chrome companion

For a web interface, the page knows what the video cannot: exact CSS sizes, font, radius, colors, and the timing and easing of each animation. The companion extension collects them from the component you pick.

## Set up (once)

1. In the AnyPoach window, press **Open the extension folder**.
2. In Chrome (Edge and Brave work the same way) open `chrome://extensions`, turn on **Developer mode**, and choose **Load unpacked** on that folder.
3. Press **Copy pairing code** in the window, open the extension popup, and paste the code once.

There is no Chrome Web Store listing yet, so you load the folder yourself.

## Capture a component

1. On your page, press **Choose a component** in the popup. A card follows the pointer with the live size, font, colors, radius, and running animations of whatever is under it. **↑** picks the parent. Click to pin it.
2. Record in AnyPoach as usual and do the interaction.
3. Press **Finish and send** in the popup, before or after stopping in AnyPoach (a session is kept for 180 s).
4. Copy the prompt.

## What the brief gains

`evidence.browserEvidence` holds:

- `components`: the measured visible descendants of the pinned element (up to 40, with size, font, colors and short text), measured when you pin and again when you finish;
- the nearby states of the component with `rect`, sizes, colors, radius, opacity, transform and shadow (read them with `anypoach_read_moment`);
- the animations with duration, delay, easing and keyframe offsets;
- the page's `devicePixelRatio` and viewport.

## What stays local

- The server listens on `127.0.0.1` only, and only while the window is open.
- It rejects any other `Host` or a page `Origin`, and requires the pairing code on every request. **Create a new pairing code** revokes the old one.
- The extension asks for `activeTab`, `scripting`, `storage`, and `http://127.0.0.1/*`, and reads text and computed styles of the picked component only.
- Nothing goes anywhere but your machine. If the connection drops, the extension retries once.
