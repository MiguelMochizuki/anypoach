import { spawn } from "node:child_process";
import { mkdtemp, mkdir, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { extractPalette } from "./palette.js";
import { approximateTiming, pixelDifference } from "./motion.js";
import type { ExtractOptions, FrameSample, InspectionResult, Keyframe } from "./types.js";

const MAX_VIDEO_BYTES = 512 * 1024 * 1024;
const MAX_DURATION_SECONDS = 30;
const DEFAULT_SAMPLE_WIDTH = 96;
const DEFAULT_SAMPLES_PER_SECOND = 12;

async function run(command: string, args: readonly string[]): Promise<Buffer> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, [...args], { stdio: ["ignore", "pipe", "pipe"] });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let outputBytes = 0;
    child.stdout.on("data", (chunk: Buffer) => {
      outputBytes += chunk.length;
      // Bound output even if a malformed file causes FFmpeg to emit too much.
      if (outputBytes > 64 * 1024 * 1024) {
        child.kill("SIGKILL");
        reject(new Error(`${command} output exceeded the 64 MiB safety limit`));
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.on("error", (error) => reject(new Error(`Could not start ${command}: ${error.message}`)));
    child.on("close", (code) => {
      if (code === 0) resolvePromise(Buffer.concat(stdout));
      else reject(new Error(`${command} exited with code ${code}: ${Buffer.concat(stderr).toString("utf8").slice(-2_000)}`));
    });
  });
}

function parseDuration(output: Buffer): number {
  const data = JSON.parse(output.toString("utf8")) as { format?: { duration?: string } };
  const duration = Number(data.format?.duration);
  if (!Number.isFinite(duration) || duration <= 0) throw new Error("Video has no valid duration");
  if (duration > MAX_DURATION_SECONDS) throw new Error(`Video is longer than the ${MAX_DURATION_SECONDS}-second limit`);
  return duration;
}

async function readFrame(videoPath: string, timeSeconds: number, width: number): Promise<FrameSample> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const actualTime = Math.max(0, timeSeconds - attempt * 0.2);
    try {
      const frame = await run("ffmpeg", [
        "-v", "error", "-ss", actualTime.toFixed(3), "-i", videoPath, "-frames:v", "1",
        "-vf", `scale=${width}:-2:flags=area`, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
      ]);
      const height = frame.length / (width * 3);
      if (!Number.isInteger(height) || height < 1) throw new Error(`Could not decode frame at ${Math.round(actualTime * 1000)} ms`);
      return { timeMs: Math.round(actualTime * 1000), pixels: frame, width, height, channels: 3 };
    } catch (error) {
      lastError = error;
      if (attempt === 3 || (error instanceof Error && error.message.startsWith("Could not start ffmpeg:"))) throw error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Could not decode a video frame");
}

async function referencePNG(sourcePath: string, timeMs: number): Promise<Buffer> {
  const png = await run("ffmpeg", [
    "-v", "error", "-ss", (timeMs / 1000).toFixed(3), "-i", sourcePath,
    "-frames:v", "1", "-vf", "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease",
    "-f", "image2pipe", "-vcodec", "png", "pipe:1",
  ]);
  if (!png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    throw new Error(`Could not decode reference image at ${timeMs} ms`);
  }
  return png;
}

function chooseKeyframes(frames: readonly FrameSample[], deltas: readonly number[]): readonly { kind: Keyframe["kind"]; index: number }[] {
  if (frames.length === 1) return [{ kind: "start", index: 0 }];
  const peakDelta = Math.max(...deltas);
  const peakIndex = Math.max(1, deltas.indexOf(peakDelta));
  const meaningfulThreshold = Math.max(0.008, peakDelta * 0.12);
  const firstMotionIndex = deltas.findIndex((delta) => delta >= meaningfulThreshold);
  const startIndex = firstMotionIndex < 0 ? 0 : firstMotionIndex;
  const settleThreshold = Math.max(0.003, peakDelta * 0.08);
  let settledIndex = frames.length - 1;
  // Require a quiet tail of at least three intervals, or the available tail.
  const quietIntervals = Math.min(3, Math.max(1, deltas.length - peakIndex));
  for (let i = peakIndex + quietIntervals; i < frames.length; i += 1) {
    const tail = deltas.slice(i - quietIntervals + 1, i + 1);
    if (tail.length === quietIntervals && tail.every((delta) => delta <= settleThreshold)) {
      settledIndex = i;
      break;
    }
  }
  const byIndex = new Map<number, Keyframe["kind"]>();
  byIndex.set(startIndex, "start");
  if (peakIndex !== startIndex && peakIndex !== settledIndex) byIndex.set(peakIndex, "peak");
  if (settledIndex !== startIndex && settledIndex !== peakIndex) byIndex.set(settledIndex, "settled");
  return [...byIndex].map(([index, kind]) => ({ index, kind })).sort((a, b) => a.index - b.index);
}

/**
 * Analyze a short MP4/MOV recording. Requires `ffmpeg` and `ffprobe` on PATH.
 * Decodes downscaled RGB samples to keep memory and CPU use predictable.
 */
export async function inspectVideo(videoFile: string, options: ExtractOptions = {}): Promise<InspectionResult> {
  const sourcePath = resolve(videoFile);
  const extension = extname(sourcePath).toLowerCase();
  if (extension !== ".mp4" && extension !== ".mov") throw new Error("Only .mp4 and .mov video files are supported");
  const fileInfo = await stat(sourcePath);
  if (!fileInfo.isFile()) throw new Error("Video path must point to a file");
  if (fileInfo.size > MAX_VIDEO_BYTES) throw new Error("Video file exceeds the 512 MiB limit");
  const durationSeconds = parseDuration(await run("ffprobe", [
    "-v", "error", "-show_entries", "format=duration", "-of", "json", sourcePath,
  ]));

  const sampleWidth = Math.max(48, Math.min(256, Math.round(options.sampleWidth ?? DEFAULT_SAMPLE_WIDTH)));
  const sampleRate = Math.max(2, Math.min(24, Math.round(options.samplesPerSecond ?? DEFAULT_SAMPLES_PER_SECOND)));
  const sampleCount = Math.max(2, Math.min(720, Math.ceil(durationSeconds * sampleRate)));
  const frames: FrameSample[] = [];
  for (let index = 0; index < sampleCount; index += 1) {
    const time = Math.min(durationSeconds - 0.001, (index / (sampleCount - 1)) * durationSeconds);
    frames.push(await readFrame(sourcePath, Math.max(0, time), sampleWidth));
  }
  const deltas = frames.slice(1).map((frame, index) => pixelDifference(frames[index]!, frame));
  const keys = chooseKeyframes(frames, deltas);
  const outputDirectory = options.outputDirectory
    ? resolve(options.outputDirectory)
    : await mkdtemp(join(tmpdir(), "poach-"));
  await mkdir(outputDirectory, { recursive: true });
  const safeBase = basename(sourcePath, extension).replace(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 48) || "capture";
  const keyframes: Keyframe[] = [];
  for (const { kind, index } of keys) {
    const frame = frames[index]!;
    const imagePath = join(outputDirectory, `${safeBase}-${kind}-${frame.timeMs}ms.png`);
    await writeFile(imagePath, await referencePNG(sourcePath, frame.timeMs));
    keyframes.push({ kind, timeMs: frame.timeMs, imagePath, motion: index === 0 ? 0 : deltas[index - 1] ?? 0 });
  }
  const motionStartMs = frames[keys[0]?.index ?? 0]?.timeMs ?? 0;
  const settled = keys.find((key) => key.kind === "settled");
  const settledTimeMs = settled ? frames[settled.index]!.timeMs : Math.round(durationSeconds * 1000);
  const durationMs = Math.max(0, settledTimeMs - motionStartMs);
  const timing = approximateTiming(frames, deltas, motionStartMs, durationMs);
  const paletteFrame = frames[keys.find((key) => key.kind === "settled")?.index ?? frames.length - 1]!;
  const palette = extractPalette(paletteFrame, options.paletteSize ?? 6);

  return {
    mediaType: "video",
    sourcePath,
    durationMs,
    keyframes,
    palette,
    timing,
  };
}

/** Analyze a still image and return one PNG keyframe plus its dominant colors. */
export async function inspectImage(imageFile: string, options: ExtractOptions = {}): Promise<InspectionResult> {
  const sourcePath = resolve(imageFile);
  const extension = extname(sourcePath).toLowerCase();
  if (![".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"].includes(extension)) {
    throw new Error("Supported still images are PNG, JPEG, WebP, TIFF, and BMP");
  }
  const fileInfo = await stat(sourcePath);
  if (!fileInfo.isFile()) throw new Error("Image path must point to a file");
  if (fileInfo.size > MAX_VIDEO_BYTES) throw new Error("Image file exceeds the 512 MiB limit");
  const probe = JSON.parse((await run("ffprobe", [
    "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", sourcePath,
  ])).toString("utf8")) as { streams?: Array<{ width?: number; height?: number }> };
  const input = probe.streams?.[0];
  if (!input?.width || !input.height) throw new Error("Image has no decodable pixel dimensions");
  const width = Math.max(48, Math.min(256, Math.round(options.sampleWidth ?? DEFAULT_SAMPLE_WIDTH)));
  const raw = await run("ffmpeg", [
    "-v", "error", "-i", sourcePath, "-frames:v", "1", "-vf", `scale=${width}:-2:flags=area`,
    "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
  ]);
  const height = raw.length / (width * 3);
  if (!Number.isInteger(height) || height < 1) throw new Error("Could not decode image pixels");
  const frame: FrameSample = { timeMs: 0, pixels: raw, width, height, channels: 3 };
  const outputDirectory = options.outputDirectory ? resolve(options.outputDirectory) : await mkdtemp(join(tmpdir(), "poach-"));
  await mkdir(outputDirectory, { recursive: true });
  const safeBase = basename(sourcePath, extension).replace(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 48) || "image";
  const imagePath = join(outputDirectory, `${safeBase}-image.png`);
  await writeFile(imagePath, await referencePNG(sourcePath, 0));
  const palette = extractPalette(frame, options.paletteSize ?? 6);
  return {
    mediaType: "image",
    sourcePath,
    durationMs: 0,
    keyframes: [{ kind: "start", timeMs: 0, imagePath, motion: 0 }],
    palette,
    timing: { durationMs: 0, bezier: [0.16, 1, 0.3, 1], token: "Still image · no motion duration" },
  };
}
