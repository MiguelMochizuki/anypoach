import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile, rm, access, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const exec = promisify(execFile);
test("shared brief carries notes and visual moments through MCP", { timeout: 30_000 }, async (t) => {
  const home = await mkdtemp(join(tmpdir(), "poach-handoff-test-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const cache = join(home, "Library/Caches/Poach");
  await mkdir(cache, { recursive: true });
  const video = join(home, "demo.mp4");
  const png = join(home, "reference.png");
  await exec("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30", "-t", "2", "-c:v", "libx264", video]);
  await exec("ffmpeg", ["-v", "error", "-i", video, "-frames:v", "1", png]);
  const brief = { version: 1, briefId: "df5ff2b4-663c-41ec-8de2-5c90e837bd82", sharedAt: Date.now() / 1000, context: "[1.00s] Expand on hover. Replace #000000 with #008080.", instruction: "Recreate the interaction", evidence: { mediaType: "video", sourcePath: video, keyframes: [{ imagePath: png, kind: "start", timeMs: 0 }] } };
  const path = join(cache, "active-brief.json");
  await writeFile(path, JSON.stringify(brief));
  const client = new Client({ name: "poach-handoff-test", version: "1.0.0" });
  const transport = new StdioClientTransport({ command: process.execPath, args: [process.env.POACH_TEST_SERVER ?? new URL("../dist/index.js", import.meta.url).pathname], env: { ...process.env, HOME: home }, stderr: "pipe" });
  await client.connect(transport);
  t.after(() => client.close());
  const shared = await client.callTool({ name: "poach_read_brief", arguments: {} });
  assert.ok(!shared.isError);
  assert.equal(shared.structuredContent.context, brief.context);
  assert.equal(shared.content.filter(item => item.type === "image").length, 1);
  const moment = await client.callTool({ name: "poach_read_moment", arguments: { timeMs: 1000 } });
  assert.ok(!moment.isError);
  assert.equal(moment.content.filter(item => item.type === "image").length, 1);
  for (const name of ["poach_read_brief", "poach_read_moment"]) {
    const args = name === "poach_read_moment" ? { timeMs: 500 } : {};
    const matching = await client.callTool({ name, arguments: { ...args, briefId: brief.briefId } });
    assert.ok(!matching.isError);
    const stale = await client.callTool({ name, arguments: { ...args, briefId: "827fb563-c2a2-4bf6-91a1-846528d715e9" } });
    assert.equal(stale.isError, true);
    assert.match(stale.content[0].text, /replaced/);
  }
  const outside = await client.callTool({ name: "poach_read_moment", arguments: { timeMs: 30000 } });
  assert.equal(outside.isError, true);
  await writeFile(path, JSON.stringify({ ...brief, sharedAt: brief.sharedAt - 86401 }));
  const expired = await client.callTool({ name: "poach_read_brief", arguments: {} });
  assert.equal(expired.isError, true);
  await assert.rejects(access(path));
});

test("connection status follows initialized clients independently", async (t) => {
  const home = await mkdtemp(join(tmpdir(), "poach-connection-test-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const directory = join(home, "Library/Caches/Poach/connections");
  const transport = () => new StdioClientTransport({
    command: process.execPath,
    args: [process.env.POACH_TEST_SERVER ?? new URL("../dist/index.js", import.meta.url).pathname],
    env: { ...process.env, HOME: home },
    stderr: "pipe",
  });
  async function expectActive(count) {
    for (let attempt = 0; attempt < 100; attempt++) {
      const files = await readdir(directory).catch(error => {
        if (error.code === "ENOENT") return [];
        throw error;
      });
      if (files.length === count) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    assert.fail(`Expected ${count} active MCP sessions`);
  }
  const uninitialized = transport();
  await uninitialized.start();
  await expectActive(0);
  await uninitialized.close();
  const a = new Client({ name: "first", version: "1" });
  const b = new Client({ name: "second", version: "1" });
  try {
    await a.connect(transport());
    await b.connect(transport());
    await expectActive(2);
    await a.close();
    await expectActive(1);
    await b.close();
    await expectActive(0);
  } finally {
    await a.close();
    await b.close();
  }
});
