export type RGB = readonly [red: number, green: number, blue: number];

export interface Keyframe {
  readonly kind: "start" | "peak" | "settled";
  readonly timeMs: number;
  readonly imagePath: string;
  /** Normalized mean absolute pixel difference from the prior sample (0–1). */
  readonly motion: number;
}

export interface MotionTiming {
  /** Time from the first meaningful change until visual settlement. */
  readonly durationMs: number;
  readonly bezier: readonly [number, number, number, number] | null;
  readonly token: string;
}

export interface InspectionResult {
  readonly mediaType: "video" | "image";
  readonly sourcePath: string;
  readonly durationMs: number;
  readonly keyframes: readonly Keyframe[];
  readonly palette: readonly string[];
  readonly timing: MotionTiming;
}

export interface ExtractOptions {
  readonly onProgress?: (stage: "motion" | "frames" | "palette") => void;
  /** Directory for PNG keyframes. Defaults to a temporary Poach directory. */
  readonly outputDirectory?: string;
  /** Maximum decoded sample width; height is scaled to preserve aspect ratio. */
  readonly sampleWidth?: number;
  /** Analysis samples per second, capped to a safe range. */
  readonly samplesPerSecond?: number;
  /** Number of dominant colors to return. */
  readonly paletteSize?: number;
}

export interface FrameSample {
  readonly timeMs: number;
  readonly pixels: Buffer;
  readonly width: number;
  readonly height: number;
  readonly channels: number;
}
