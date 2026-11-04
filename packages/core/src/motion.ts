import type { FrameSample, MotionTiming } from "./types.js";

/** Mean absolute RGB difference normalized to 0–1. */
export function pixelDifference(left: FrameSample, right: FrameSample): number {
  if (left.width !== right.width || left.height !== right.height || left.channels !== right.channels) {
    throw new Error("Frame dimensions must match to compute motion");
  }
  let total = 0;
  for (let index = 0; index < left.pixels.length; index += left.channels) {
    // Luma weighting reduces sensitivity to small chroma noise.
    const lumaA = left.pixels[index]! * 0.2126 + left.pixels[index + 1]! * 0.7152 + left.pixels[index + 2]! * 0.0722;
    const lumaB = right.pixels[index]! * 0.2126 + right.pixels[index + 1]! * 0.7152 + right.pixels[index + 2]! * 0.0722;
    total += Math.abs(lumaA - lumaB);
  }
  return total / (left.width * left.height * 255);
}

/** Fit a monotonic cubic Bézier to cumulative frame-change progress. */
export function approximateTiming(
  frames: readonly FrameSample[],
  deltas: readonly number[],
  startMs: number,
  durationMs: number,
): MotionTiming {
  if (durationMs <= 0 || deltas.length === 0) {
    return { durationMs: Math.max(0, durationMs), bezier: [0.16, 1, 0.3, 1], token: `${Math.max(0, durationMs)}ms • cubic-bezier(0.16, 1, 0.3, 1)` };
  }
  const endMs = startMs + durationMs;
  const selected = frames.map((frame, index) => ({ frame, delta: deltas[index - 1] ?? 0 }))
    .filter(({ frame }) => frame.timeMs >= startMs && frame.timeMs <= endMs);
  const movement = selected.map(({ delta }) => delta);
  const total = movement.reduce((sum, value) => sum + value, 0);
  if (total < 1e-6 || selected.length < 3) {
    return { durationMs, bezier: [0.16, 1, 0.3, 1], token: `${durationMs}ms • cubic-bezier(0.16, 1, 0.3, 1)` };
  }
  const cumulative = [0];
  for (const value of movement.slice(1)) cumulative.push(cumulative.at(-1)! + value);
  const points = selected.map(({ frame }, index) => ({
    x: Math.max(0, Math.min(1, (frame.timeMs - startMs) / durationMs)),
    y: cumulative[index]! / total,
  }));
  const error = (x1: number, y1: number, x2: number, y2: number): number => points.reduce((sum, point) => {
    const t = point.x;
    const estimate = 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3;
    return sum + (estimate - point.y) ** 2;
  }, (x1 + x2) * 0.001);
  let best: readonly [number, number, number, number] = [0.16, 1, 0.3, 1];
  let bestError = Number.POSITIVE_INFINITY;
  for (let y1Index = 0; y1Index <= 10; y1Index += 1) {
    for (let y2Index = 0; y2Index <= 10; y2Index += 1) {
      const y1 = y1Index / 10;
      const y2 = y2Index / 10;
      const candidate: readonly [number, number, number, number] = [0.16, y1, 0.3, y2];
      const candidateError = error(candidate[0], candidate[1], candidate[2], candidate[3]);
      if (candidateError < bestError) { best = candidate; bestError = candidateError; }
    }
  }
  const bezier = best.map((value) => Number(value.toFixed(2))) as unknown as readonly [number, number, number, number];
  const curve = `cubic-bezier(${bezier.join(", ")})`;
  return { durationMs, bezier, token: `${durationMs}ms • ${curve}` };
}
