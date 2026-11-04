import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { inspectRecording, inspectVideo, readVideoMoment } from "../dist/index.js";

const exec = promisify(execFile);

test("native recorder overrun is clipped while imported videos stay bounded", { timeout: 120_000 }, async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "poach-boundary-test-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const source = join(directory, "overrun.mov");
  await exec("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30",
    "-t", "31.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", source]);
  await assert.rejects(inspectVideo(source), /30-second limit/);
  const result = await inspectRecording(source);
  assert.notEqual(result.sourcePath, source);
  t.after(() => rm(dirname(result.sourcePath), { recursive: true, force: true }));
  for (const folder of new Set(result.keyframes.map(frame => dirname(frame.imagePath)))) {
    t.after(() => rm(folder, { recursive: true, force: true }));
  }
  const { stdout } = await exec("ffprobe", ["-v", "error", "-show_entries", "format=duration",
    "-of", "default=nw=1:nk=1", result.sourcePath]);
  assert.equal(Number(stdout), 30);
  assert.ok(result.keyframes.length > 0);
  const frame = await readVideoMoment(result.sourcePath, 29_900);
  assert.deepEqual([...frame.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  await assert.rejects(readVideoMoment(result.sourcePath, 30_000));
});
