// Regenerate python/tests/golden from the TS core (the oracle).
//   cd python && uv run python -c "from pathlib import Path; from tests.fixtures import build_all; build_all(Path('/tmp/poach-fixtures'))"
//   node tools/make_goldens.mjs /tmp/poach-fixtures
import { copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { inspectImage, inspectRecording, inspectVideo } from "../../packages/core/dist/index.js";

const fixtures = resolve(process.argv[2] ?? "");
const golden = fileURLToPath(new URL("../tests/golden/", import.meta.url));
await rm(golden, { recursive: true, force: true });
await mkdir(golden, { recursive: true });

const cases = [
  ["motion", "motion.mov", inspectVideo], ["static", "static.mov", inspectVideo],
  ["sparse", "sparse.mov", inspectVideo], ["image", "image.png", inspectImage],
  ["overrun", "overrun.mov", inspectRecording],
];
for (const [name, file, inspect] of cases) {
  const out = await mkdtemp(join(tmpdir(), "poach-golden-"));
  const result = await inspect(join(fixtures, file), { outputDirectory: out });
  for (const frame of result.keyframes) {
    await copyFile(frame.imagePath, join(golden, `${name}-${frame.kind}.png`));
    frame.imagePath = `${name}-${frame.kind}.png`;
  }
  delete result.sourcePath;
  await writeFile(join(golden, `${name}.json`), JSON.stringify(result, null, 2) + "\n");
  await rm(out, { recursive: true, force: true });
  console.log(basename(file), result.keyframes.map((k) => `${k.kind}@${k.timeMs}`).join(" "), result.timing.token);
}
