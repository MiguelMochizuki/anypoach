"""Drive the Python MCP server (and, when built, the TS one) with a real stdio client and compare behavior."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
TS_SERVER = ROOT / "packages/mcp-server/dist/index.js"
PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def sp(server, home):
    cache = home / "Library/Caches/Poach"  # the TS server derives this from HOME
    env = {**os.environ, "HOME": str(home), "POACH_CACHE_DIR": str(cache)}
    if server == "ts":
        return StdioServerParameters(command="node", args=[str(TS_SERVER)], env=env)
    return StdioServerParameters(command=sys.executable, args=["-m", "poach.mcp.server"], env=env)


@pytest.fixture(params=["python", "ts"])
def server(request):
    if request.param == "ts" and not (TS_SERVER.exists() and shutil.which("node")):
        pytest.skip("TS server is not built")
    return request.param


@asynccontextmanager
async def connect(server, home):
    async with stdio_client(sp(server, home)) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


def structured(result):
    return getattr(result, "structured_content", None) or result.structuredContent


def is_error(result):
    return bool(getattr(result, "is_error", getattr(result, "isError", False)))


def texts(result):
    return [c.text for c in result.content if c.type == "text"]


def images(result):
    return [c for c in result.content if c.type == "image"]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def make_video(path, color, after=None):
    """5 fps mpeg4: eight frames of `color`, then two of `after` (a color change after the last drag)."""
    if after is None:
        ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s=96x64:r=5:d=2", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(path))
    else:
        ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s=96x64:r=5:d=1.6", "-f", "lavfi", "-i", f"color=c={after}:s=96x64:r=5:d=0.4",
               "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(path))


def event(t, kind, x, y, inside=True):
    return {"timeMs": t, "kind": kind, "x": x, "y": y, "button": "left", "withinCapture": inside}


@pytest.fixture
def home(tmp_path):
    (tmp_path / "Library/Caches/Poach").mkdir(parents=True)
    return tmp_path


def base_brief(home):
    video, png = home / "demo.mp4", home / "reference.png"
    make_video(video, "0x008080", "red")
    ffmpeg("-i", str(video), "-frames:v", "1", str(png))
    return {"version": 1, "briefId": "df5ff2b4-663c-41ec-8de2-5c90e837bd82", "sharedAt": time.time(),
            "context": "[1.00s] Expand on hover. Replace #000000 with #008080.", "instruction": "Recreate the interaction",
            "evidence": {"mediaType": "video", "sourcePath": str(video),
                         "keyframes": [{"imagePath": str(png), "kind": "start", "timeMs": 0}],
                         "annotations": [{"timeMs": 1000, "text": "The heart fills on click."}],
                         "pointerTrace": {"available": True, "coordinateSpace": "normalized-capture-bounds", "origin": "top-left",
                                          "boundsWidth": 800, "boundsHeight": 600, "sampleIntervalMs": 1000 / 120,
                                          "sampleCount": 132, "insideSampleCount": 110, "buttonSampleCount": 12,
                                          "scrollCaptured": False, "truncated": False,
                                          "events": [event(900, "down", 0.5, 0.5), event(980, "up", 0.5, 0.5),
                                                     event(1200, "down", 0.1, 0.2), event(1250, "drag", 0.4, 0.5),
                                                     event(1400, "up", 0.8, 0.8),
                                                     event(1700, "down", 0.998, 0.5), event(1800, "up", 1, 0.5, False),
                                                     event(1800, "down", 0.998, 0.5), event(1900, "drag", 1, 0.5, False),
                                                     event(2000, "up", 1, 0.5, False)]}}}


def write_active(home, brief):
    (home / "Library/Caches/Poach/active-brief.json").write_text(json.dumps(brief))


def test_shared_brief_carries_notes_and_visual_moments_through_mcp(server, home):
    brief = base_brief(home)
    brief["evidence"]["browserEvidence"] = {"videoOffsetMs": -100,
        "events": [{"atMs": 1075, "type": "drop", "target": {"tag": "div"}}],
        "states": [{"atMs": 1250, "text": "Uploaded", "styles": {
            "fontFamily": '"Fixture Sans", sans-serif', "fontSize": "24px", "fontWeight": "650", "fontStyle": "italic",
            "lineHeight": "30px", "letterSpacing": "-0.5px", "opacity": "1"}}, {"atMs": 1900, "text": "Too big"}]}
    write_active(home, brief)

    async def scenario():
        async with connect(server, home) as client:
            shared = await client.call_tool("poach_read_brief", {})
            assert not is_error(shared)
            sc = structured(shared)
            assert sc["context"] == brief["context"]
            assert sc["evidence"]["browserEvidence"] == brief["evidence"]["browserEvidence"]
            assert len(images(shared)) == 4
            assert any(t.startswith("After drag release: 1699 ms") for t in texts(shared))
            imgs = images(shared)
            assert imgs[1].data != imgs[-1].data, "the tail frame shows the post-release color change"
            actions = sc["evidence"]["interactionActions"]["actions"]
            assert [a["kind"] for a in actions] == ["click", "drag", "drag", "drag"]
            assert sc["evidence"]["interactionActions"]["samplingBased"] is True
            assert (actions[0]["timeMs"], actions[1]["durationMs"], actions[2]["timeMs"], actions[2]["durationMs"],
                    actions[3]["durationMs"]) == (900, 200, 1700, 100, 200)
            assert sc["evidence"]["pointerTrace"]["sampleCount"] == 132

            two = json.loads(json.dumps(brief))
            two["evidence"]["pointerTrace"]["events"][:0] = [event(100, "down", 0.1, 0.1), event(200, "drag", 0.3, 0.3),
                                                             event(300, "up", 0.4, 0.4)]
            write_active(home, two)
            multiple = await client.call_tool("poach_read_brief", {"briefId": brief["briefId"]})
            assert not is_error(multiple)
            text = texts(multiple)
            for prefix in ("Drag release candidate at 300 ms", "After drag release: 1199 ms",
                           "Drag release candidate at 1400 ms", "After drag release: 1699 ms"):
                assert any(t.startswith(prefix) for t in text), prefix
            write_active(home, brief)

            moment = await client.call_tool("poach_read_moment", {"timeMs": 1000})
            assert not is_error(moment) and len(images(moment)) == 1
            text = texts(moment)[0]
            assert "The heart fills on click" in text and "sample-derived click/drag candidates" in text
            assert '"type":"drop"' in text and '"estimatedVideoMs":975' in text
            assert '"text":"Uploaded"' in text and '"estimatedVideoMs":1150' in text
            line = next(l for l in text.split("\n") if l.startswith("Nearby Chrome evidence"))
            upload = json.loads(line[line.index("): ") + 3:])[1]
            typography = {k: v for k, v in brief["evidence"]["browserEvidence"]["states"][0]["styles"].items() if k != "opacity"}
            assert upload["styles"] == typography
            assert "Too big" not in text
            assert ("Pointer trace summary: 132 samples, 110 inside the capture, 12 with a button held, "
                    "10 recorded pointer events, and 4 summarized clicks or drags.") in text

            for name, args in (("poach_read_brief", {}), ("poach_read_moment", {"timeMs": 500})):
                assert not is_error(await client.call_tool(name, {**args, "briefId": brief["briefId"]}))
                stale = await client.call_tool(name, {**args, "briefId": "827fb563-c2a2-4bf6-91a1-846528d715e9"})
                assert is_error(stale) and "replaced" in texts(stale)[0]
            assert is_error(await client.call_tool("poach_read_moment", {"timeMs": 30000}))

            empty = json.loads(json.dumps(brief))
            empty["evidence"]["pointerTrace"].update(sampleCount=44, insideSampleCount=40, buttonSampleCount=0, events=[])
            write_active(home, empty)
            text = texts(await client.call_tool("poach_read_moment", {"timeMs": 1000}))[0]
            assert "Pointer trace summary: 44 samples, 40 inside the capture, 0 with a button held, 0 recorded pointer events, and 0 summarized clicks or drags." in text

            gone = json.loads(json.dumps(brief))
            gone["evidence"]["pointerTrace"].update(available=False, sampleCount=0, insideSampleCount=0, buttonSampleCount=0, events=[])
            write_active(home, gone)
            text = texts(await client.call_tool("poach_read_moment", {"timeMs": 1000}))[0]
            assert "No native pointer trace was included" in text and "Pointer trace summary:" not in text

            cut = json.loads(json.dumps(brief))
            cut["evidence"]["pointerTrace"].update(truncated=True, events=[event(990, "down", 0.5, 0.5)])
            write_active(home, cut)
            text = texts(await client.call_tool("poach_read_moment", {"timeMs": 1000}))[0]
            assert "Trace reached its event limit; later actions may be incomplete" in text
            assert "Incomplete button-down without a matching release" in text

            write_active(home, {**brief, "sharedAt": brief["sharedAt"] - 86401})
            expired = await client.call_tool("poach_read_brief", {})
            assert is_error(expired) and "expired" in texts(expired)[0]
            assert (home / "Library/Caches/Poach/active-brief.json").exists()

    asyncio.run(scenario())


def test_archived_briefs_remain_readable_by_id(server, home):
    cache = home / "Library/Caches/Poach"
    archive = cache / "briefs"
    archive.mkdir()
    make_video(home / "older.mp4", "red")
    make_video(home / "latest.mp4", "blue")
    older = {"version": 1, "briefId": "a2e9bf72-26b9-4a9d-888a-fc47ad798813", "sharedAt": time.time(),
             "context": "First prompt: make the PNG badge red.", "instruction": "Recreate the recorded interaction.",
             "evidence": {"mediaType": "video", "sourcePath": str(home / "older.mp4"), "keyframes": [], "annotations": []}}
    latest = {**older, "briefId": "b7f24322-2d3c-42e9-8d72-4d5d7ef96441", "context": "Second prompt: make the dropzone compact.",
              "evidence": {**older["evidence"], "sourcePath": str(home / "latest.mp4")}}
    (archive / f"{older['briefId']}.json").write_text(json.dumps(older))
    write_active(home, latest)

    async def scenario():
        async with connect(server, home) as client:
            first = await client.call_tool("poach_read_brief", {"briefId": older["briefId"], "includeKeyframes": False})
            assert not is_error(first) and structured(first)["context"] == older["context"]
            recent = await client.call_tool("poach_read_brief", {"includeKeyframes": False})
            assert structured(recent)["briefId"] == latest["briefId"]
            old_moment = await client.call_tool("poach_read_moment", {"briefId": older["briefId"], "timeMs": 500})
            new_moment = await client.call_tool("poach_read_moment", {"briefId": latest["briefId"], "timeMs": 500})
            assert not is_error(old_moment) and not is_error(new_moment)
            assert images(old_moment)[0].data != images(new_moment)[0].data, "each brief ID should read its own recording"

            preset = {**latest, "briefId": "c87701b6-62ae-44be-bd74-34604931a854", "evidence": {
                **latest["evidence"], "sourcePath": "", "annotations": [{"timeMs": 500, "text": "The badge expands here."}],
                "keyframes": [{"kind": "peak", "timeMs": 500, "imagePath": str(home / "preset.png")}],
                "visualFontMatch": {"family": "Georgia", "face": "Bold Italic", "postScriptName": "Georgia-BoldItalic",
                                    "region": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1}}}}
            (home / "preset.png").write_bytes(__import__("base64").b64decode(images(new_moment)[0].data))
            (archive / f"{preset['briefId']}.json").write_text(json.dumps(preset))
            saved = await client.call_tool("poach_read_brief", {"briefId": preset["briefId"]})
            assert not is_error(saved)
            assert structured(saved)["evidence"]["visualFontMatch"] == preset["evidence"]["visualFontMatch"]
            assert images(saved)[0].data == images(new_moment)[0].data
            kept = await client.call_tool("poach_read_moment", {"briefId": preset["briefId"], "timeMs": 500})
            assert is_error(kept) and "Use poach_read_brief to see its saved frames" in texts(kept)[0]

            path = archive / f"{older['briefId']}.json"
            path.write_text(json.dumps({**older, "sharedAt": older["sharedAt"] - 86401}))
            expired = await client.call_tool("poach_read_brief", {"briefId": older["briefId"]})
            assert is_error(expired) and "expired" in texts(expired)[0]
            assert not path.exists() and (cache / "active-brief.json").exists()

    asyncio.run(scenario())


def test_connection_status_follows_initialized_clients(server, home):
    directory = home / "Library/Caches/Poach/connections"

    async def active(count):
        for _ in range(150):
            if (len(list(directory.iterdir())) if directory.exists() else 0) == count:
                return
            await asyncio.sleep(0.02)
        raise AssertionError(f"Expected {count} active MCP sessions")

    async def scenario():
        async with stdio_client(sp(server, home)):  # started, never initialized
            await asyncio.sleep(0.5)
            await active(0)
        async with connect(server, home):
            async with connect(server, home):
                await active(2)
            await active(1)
        await active(0)

    asyncio.run(scenario())


def test_stdout_carries_only_protocol_messages(server, home):
    params = sp(server, home)
    process = subprocess.Popen([params.command, *params.args], env=params.env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "poach_read_brief", "arguments": {}}}]
    out, _ = process.communicate("".join(json.dumps(r) + "\n" for r in requests), timeout=20)
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines and all(json.loads(l)["jsonrpc"] == "2.0" for l in lines)


def test_tools_match_the_ts_server_names_descriptions_and_inputs(home):
    if not (TS_SERVER.exists() and shutil.which("node")):
        pytest.skip("TS server is not built")

    async def listing(which):
        async with connect(which, home) as client:
            tools = (await client.list_tools()).tools
            return {t.name: (t.title, t.description, set(t.input_schema["properties"] if hasattr(t, "input_schema") else t.inputSchema["properties"]),
                             set((t.input_schema if hasattr(t, "input_schema") else t.inputSchema).get("required", []))) for t in tools}

    assert asyncio.run(listing("python")) == asyncio.run(listing("ts"))
    assert uuid.UUID("827fb563-c2a2-4bf6-91a1-846528d715e9")


def test_inspect_tools_return_results_and_report_errors(clips, home):
    async def scenario():
        async with connect("python", home) as client:
            video = await client.call_tool("poach_inspect", {"videoPath": str(clips["static"]), "outputDirectory": str(home / "out")})
            assert not is_error(video)
            data = structured(video)
            assert data["mediaType"] == "video" and [k["kind"] for k in data["keyframes"]] == ["start"]
            assert (home / "out").is_dir() and json.loads(texts(video)[0]) == data
            still = await client.call_tool("poach_inspect_image", {"imagePath": str(clips["image"])})
            assert structured(still)["timing"]["token"] == "Still image · no motion duration"
            missing = await client.call_tool("poach_inspect", {"videoPath": str(home / "missing.mov")})
            assert is_error(missing) and texts(missing)[0].startswith("Poach could not inspect this video: ")
            bad = await client.call_tool("poach_inspect_image", {"imagePath": str(clips["static"])})
            assert is_error(bad) and texts(bad)[0].startswith("Poach could not inspect this image: ")

    asyncio.run(scenario())
