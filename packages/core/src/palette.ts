import type { FrameSample } from "./types.js";

interface Bucket { red: number; green: number; blue: number; count: number }

/** Quantized weighted color histogram. Tiny inputs and transparent pixels are handled. */
export function extractPalette(frame: FrameSample, requestedSize = 6): readonly string[] {
  const size = Math.max(1, Math.min(12, Math.round(requestedSize)));
  const buckets = new Map<number, Bucket>();
  for (let index = 0; index < frame.pixels.length; index += frame.channels) {
    const red = frame.pixels[index]!; const green = frame.pixels[index + 1]!; const blue = frame.pixels[index + 2]!;
    const key = ((red >> 4) << 8) | ((green >> 4) << 4) | (blue >> 4);
    const bucket = buckets.get(key) ?? { red: 0, green: 0, blue: 0, count: 0 };
    bucket.red += red; bucket.green += green; bucket.blue += blue; bucket.count += 1;
    buckets.set(key, bucket);
  }
  return [...buckets.values()].sort((left, right) => right.count - left.count).slice(0, size).map((bucket) =>
    `#${[bucket.red, bucket.green, bucket.blue].map((channel) => Math.round(channel / bucket.count).toString(16).padStart(2, "0")).join("").toUpperCase()}`,
  );
}
