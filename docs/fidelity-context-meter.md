# Context meter fidelity check

On November 4, 2026, we compared the local context meter with the MOV shared by Poach. The reference recording runs for 13.17 seconds. The 7.336-second timing estimate in its brief spans several interactions. Treating that estimate as the duration of a single hover or compact animation would give the wrong result.

| Check | Recorded interaction | Local recreation |
| --- | --- | --- |
| Hover Files | The reading changes from the total to **46.1K Files**. Files stays bright while the other segments dim. | The label matched. During the hover transition, the Chat segment reached roughly 40% opacity while the number was still rolling. |
| Compact | The reading settles at **97.4K of 200K** and the button changes to **Undo**. The cyan segment retains 28.1% of its original width. | The same total and button appear. The cyan segment retains 28.0% of its original width. |
| Compact timing | The middle 80% of the cyan segment's shrink takes approximately **283 ms**. | The same portion took **200 ms** in both runs, about 83 ms faster. |
| Undo | The original **175.6K** total and bar return. | The displayed digits return to **175.6K** after the interrupted hover and compact sequence. |

## How to repeat the interruption

1. Open `apps/benchmark/context-meter.html` in Chrome and move the pointer to Files.
2. While the digits are still rolling, move directly to Compact and click. In the automated check, the pointer stayed over Files for 75 ms before moving.
3. After 600 ms, check the visible number, its accessible reading, and the bar. Both readings should show **97.4K**, all segments should regain full opacity, and every category chip should lose its hover highlight.
4. Click Undo. The visible number should settle at **175.6K**.

Both local runs passed. The saved recording moves through other categories between Files and Compact, so the immediate interruption sequence has only been verified on the recreation.

## How the timing was measured

For the reference, we sampled the middle of the bar in the Poach MOV at 60 Hz and counted the contiguous cyan pixels during Compact. Its width fell from 356 to 100 capture pixels. For the local render, we sampled the segment's bounding box on each browser animation frame. Its width fell from 179.73 to 50.31 CSS pixels. Each measurement uses its own starting and ending widths to account for display scale. The reported interval starts at the first sample past 10% progress and ends at the first sample past 90%. Frame sampling limits precision to roughly a frame at each endpoint.
