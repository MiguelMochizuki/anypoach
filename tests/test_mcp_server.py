"""Drive the MCP server with a real stdio client."""
import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def sp(server, home):
    cache = home / "Library/Caches/AnyPoach"
    env = {**os.environ, "HOME": str(home), "ANYPOACH_CACHE_DIR": str(cache)}
    return StdioServerParameters(command=sys.executable, args=["-m", "anypoach.mcp.server"], env=env)


@pytest.fixture
def server():
    return "python"


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
    (tmp_path / "Library/Caches/AnyPoach").mkdir(parents=True)
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
    (home / "Library/Caches/AnyPoach/active-brief.json").write_text(json.dumps(brief))


def chrome_line(text):
    line = next(l for l in text.split("\n") if l.startswith("Nearby Chrome evidence"))
    return line[: line.index("): ")], json.loads(line[line.index("): ") + 3:])


def test_moment_reports_the_pages_own_sizes_and_animation_timing(server, home):
    brief = base_brief(home)
    brief["evidence"]["browserEvidence"] = {"videoOffsetMs": 0, "devicePixelRatio": 2, "viewport": {"width": 1280, "height": 720},
        "events": [],
        "states": [{"atMs": 1000, "text": "Go", "rect": [10, 20, 240.5, 48], "styles": {
            "fontSize": "16px", "width": "240.5px", "height": "48px", "borderRadius": "12px", "opacity": "1",
            "transform": "none", "color": "rgb(0, 0, 0)", "backgroundColor": "rgb(35, 120, 255)", "boxShadow": "none",
            "padding": "dropped"}}],
        "animations": [
            {"atMs": 1000, "target": {"tag": "button"}, "durationMs": 334, "delayMs": 20,
             "easing": "cubic-bezier(0.16, 0.9, 0.3, 1)", "keyframes": [{"offset": 0, "easing": "linear", "styles": {}},
                                                                        {"offset": 1, "easing": "linear", "styles": {}}]},
            {"atMs": 1000, "durationMs": "not a number"}]}
    write_active(home, brief)

    async def scenario():
        async with connect(server, home) as client:
            moment = await client.call_tool("anypoach_read_moment", {"timeMs": 1000})
            assert not is_error(moment), texts(moment)
            text = texts(moment)[0]
            header, items = chrome_line(text)
            assert "devicePixelRatio 2" in header and "1280x720" in header
            state = next(i for i in items if i.get("text") == "Go")
            assert state["rect"] == [10, 20, 240.5, 48]
            assert state["styles"]["width"] == "240.5px" and state["styles"]["borderRadius"] == "12px"
            assert state["styles"]["backgroundColor"] == "rgb(35, 120, 255)" and "padding" not in state["styles"]
            animation = next(i for i in items if "easing" in i)
            assert animation["durationMs"] == 334 and animation["delayMs"] == 20
            assert animation["easing"] == "cubic-bezier(0.16, 0.9, 0.3, 1)" and animation["keyframeOffsets"] == [0, 1]
            assert sum("easing" in i for i in items) == 1, "the malformed animation is skipped, not fatal"

    asyncio.run(scenario())


def test_moment_always_includes_the_state_in_force_even_when_it_is_old(server, home):
    brief = base_brief(home)
    brief["evidence"]["browserEvidence"] = {"videoOffsetMs": -11075, "events": [],
        "states": [{"atMs": 0, "text": "Hero", "rect": [0, 0, 1468, 720], "styles": {"width": "1468px", "fontSize": "16px"}}]}
    write_active(home, brief)

    async def scenario():
        async with connect(server, home) as client:
            moment = await client.call_tool("anypoach_read_moment", {"timeMs": 100})
            _, items = chrome_line(texts(moment)[0])
            assert items[0]["baseline"] is True and items[0]["styles"]["width"] == "1468px"
            assert items[0]["estimatedVideoMs"] == -11075

    asyncio.run(scenario())


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
            shared = await client.call_tool("anypoach_read_brief", {})
            assert not is_error(shared), texts(shared)
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
            multiple = await client.call_tool("anypoach_read_brief", {"briefId": brief["briefId"]})
            assert not is_error(multiple)
            text = texts(multiple)
            for prefix in ("Drag release candidate at 300 ms", "After drag release: 1199 ms",
                           "Drag release candidate at 1400 ms", "After drag release: 1699 ms"):
                assert any(t.startswith(prefix) for t in text), prefix
            write_active(home, brief)

            moment = await client.call_tool("anypoach_read_moment", {"timeMs": 1000})
            assert not is_error(moment) and len(images(moment)) == 1
            text = texts(moment)[0]
            assert "The heart fills on click" in text and "sample-derived click/drag candidates" in text
            assert '"type":"drop"' in text and '"estimatedVideoMs":975' in text
            assert '"text":"Uploaded"' in text and '"estimatedVideoMs":1150' in text
            line = next(l for l in text.split("\n") if l.startswith("Nearby Chrome evidence"))
            upload = json.loads(line[line.index("): ") + 3:])[1]
            assert upload["styles"] == brief["evidence"]["browserEvidence"]["states"][0]["styles"]
            assert "Too big" not in text
            assert ("Pointer trace summary: 132 samples, 110 inside the capture, 12 with a button held, "
                    "10 recorded pointer events, and 4 summarized clicks or drags.") in text

            for name, args in (("anypoach_read_brief", {}), ("anypoach_read_moment", {"timeMs": 500})):
                assert not is_error(await client.call_tool(name, {**args, "briefId": brief["briefId"]}))
                stale = await client.call_tool(name, {**args, "briefId": "827fb563-c2a2-4bf6-91a1-846528d715e9"})
                assert is_error(stale) and "replaced" in texts(stale)[0]
            assert is_error(await client.call_tool("anypoach_read_moment", {"timeMs": 30000}))

            empty = json.loads(json.dumps(brief))
            empty["evidence"]["pointerTrace"].update(sampleCount=44, insideSampleCount=40, buttonSampleCount=0, events=[])
            write_active(home, empty)
            text = texts(await client.call_tool("anypoach_read_moment", {"timeMs": 1000}))[0]
            assert "Pointer trace summary: 44 samples, 40 inside the capture, 0 with a button held, 0 recorded pointer events, and 0 summarized clicks or drags." in text

            gone = json.loads(json.dumps(brief))
            gone["evidence"]["pointerTrace"].update(available=False, sampleCount=0, insideSampleCount=0, buttonSampleCount=0, events=[])
            write_active(home, gone)
            text = texts(await client.call_tool("anypoach_read_moment", {"timeMs": 1000}))[0]
            assert "No native pointer trace was included" in text and "Pointer trace summary:" not in text

            cut = json.loads(json.dumps(brief))
            cut["evidence"]["pointerTrace"].update(truncated=True, events=[event(990, "down", 0.5, 0.5)])
            write_active(home, cut)
            text = texts(await client.call_tool("anypoach_read_moment", {"timeMs": 1000}))[0]
            assert "Trace reached its event limit; later actions may be incomplete" in text
            assert "Incomplete button-down without a matching release" in text

            write_active(home, {**brief, "sharedAt": brief["sharedAt"] - 86401})
            expired = await client.call_tool("anypoach_read_brief", {})
            assert is_error(expired) and "expired" in texts(expired)[0]
            assert (home / "Library/Caches/AnyPoach/active-brief.json").exists()

    asyncio.run(scenario())


def test_archived_briefs_remain_readable_by_id(server, home):
    cache = home / "Library/Caches/AnyPoach"
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
            first = await client.call_tool("anypoach_read_brief", {"briefId": older["briefId"], "includeKeyframes": False})
            assert not is_error(first) and structured(first)["context"] == older["context"]
            recent = await client.call_tool("anypoach_read_brief", {"includeKeyframes": False})
            assert structured(recent)["briefId"] == latest["briefId"]
            old_moment = await client.call_tool("anypoach_read_moment", {"briefId": older["briefId"], "timeMs": 500})
            new_moment = await client.call_tool("anypoach_read_moment", {"briefId": latest["briefId"], "timeMs": 500})
            assert not is_error(old_moment) and not is_error(new_moment)
            assert images(old_moment)[0].data != images(new_moment)[0].data, "each brief ID should read its own recording"

            preset = {**latest, "briefId": "c87701b6-62ae-44be-bd74-34604931a854", "evidence": {
                **latest["evidence"], "sourcePath": "", "annotations": [{"timeMs": 500, "text": "The badge expands here."}],
                "keyframes": [{"kind": "peak", "timeMs": 500, "imagePath": str(home / "preset.png")}],
                "visualFontMatch": {"family": "Georgia", "face": "Bold Italic", "postScriptName": "Georgia-BoldItalic",
                                    "region": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1}}}}
            (home / "preset.png").write_bytes(__import__("base64").b64decode(images(new_moment)[0].data))
            (archive / f"{preset['briefId']}.json").write_text(json.dumps(preset))
            saved = await client.call_tool("anypoach_read_brief", {"briefId": preset["briefId"]})
            assert not is_error(saved)
            assert structured(saved)["evidence"]["visualFontMatch"] == preset["evidence"]["visualFontMatch"]
            assert images(saved)[0].data == images(new_moment)[0].data
            kept = await client.call_tool("anypoach_read_moment", {"briefId": preset["briefId"], "timeMs": 500})
            assert is_error(kept) and "Use anypoach_read_brief to see its saved frames" in texts(kept)[0]

            path = archive / f"{older['briefId']}.json"
            path.write_text(json.dumps({**older, "sharedAt": older["sharedAt"] - 86401}))
            expired = await client.call_tool("anypoach_read_brief", {"briefId": older["briefId"]})
            assert is_error(expired) and "expired" in texts(expired)[0]
            assert not path.exists() and (cache / "active-brief.json").exists()

    asyncio.run(scenario())


def test_connection_status_follows_initialized_clients(server, home):
    directory = home / "Library/Caches/AnyPoach/connections"

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
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "anypoach_read_brief", "arguments": {}}}]
    out, _ = process.communicate("".join(json.dumps(r) + "\n" for r in requests), timeout=20)
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines and all(json.loads(l)["jsonrpc"] == "2.0" for l in lines)



def test_inspect_tools_return_results_and_report_errors(clips, home):
    async def scenario():
        async with connect("python", home) as client:
            video = await client.call_tool("anypoach_inspect", {"videoPath": str(clips["static"]), "outputDirectory": str(home / "out")})
            assert not is_error(video)
            data = structured(video)
            assert data["mediaType"] == "video" and [k["kind"] for k in data["keyframes"]] == ["start"]
            assert (home / "out").is_dir() and json.loads(texts(video)[0]) == data
            still = await client.call_tool("anypoach_inspect_image", {"imagePath": str(clips["image"])})
            assert structured(still)["timing"]["token"] == "Still image · no motion duration"
            missing = await client.call_tool("anypoach_inspect", {"videoPath": str(home / "missing.mov")})
            assert is_error(missing) and texts(missing)[0].startswith("AnyPoach could not inspect this video: ")
            bad = await client.call_tool("anypoach_inspect_image", {"imagePath": str(clips["static"])})
            assert is_error(bad) and texts(bad)[0].startswith("AnyPoach could not inspect this image: ")

    asyncio.run(scenario())


def with_capture(home, width, height):
    brief = base_brief(home)
    brief["evidence"]["capture"] = {"widthPx": width, "heightPx": height, "deviceScale": None, "imageMaxSize": 1280}
    write_active(home, brief)
    return brief


def test_keyframe_caption_states_the_native_size(server, home):
    with_capture(home, 192, 128)

    async def scenario():
        async with connect(server, home) as client:
            result = await client.call_tool("anypoach_read_brief", {})
            assert not is_error(result), texts(result)
            assert any(t == "start at 0 ms (96x64, reduced from 192x128 (x0.50))" for t in texts(result)), texts(result)
    asyncio.run(scenario())


def test_odd_native_size_is_exact(server, home):
    with_capture(home, 1853, 961)

    async def scenario():
        async with connect(server, home) as client:
            result = await client.call_tool("anypoach_read_brief", {})
            assert any("96x64, reduced from 1853x961 (x0.05)" in t for t in texts(result)), texts(result)
    asyncio.run(scenario())


def test_native_size_image_says_so(server, home):
    with_capture(home, 96, 64)

    async def scenario():
        async with connect(server, home) as client:
            result = await client.call_tool("anypoach_read_brief", {})
            assert any(t == "start at 0 ms (96x64, native size)" for t in texts(result)), texts(result)
    asyncio.run(scenario())


def test_brief_without_capture_gets_no_scale_note(server, home):
    write_active(home, base_brief(home))

    async def scenario():
        async with connect(server, home) as client:
            result = await client.call_tool("anypoach_read_brief", {})
            assert not is_error(result)
            assert "start at 0 ms" in texts(result)
            assert not any("reduced from" in t or "native size" in t for t in texts(result))
            moment = await client.call_tool("anypoach_read_moment", {"timeMs": 0})
            assert not is_error(moment) and not any("reduced from" in t for t in texts(moment))
    asyncio.run(scenario())


def test_read_moment_caption_states_the_scale(server, home):
    with_capture(home, 192, 128)

    async def scenario():
        async with connect(server, home) as client:
            moment = await client.call_tool("anypoach_read_moment", {"timeMs": 0})
            assert not is_error(moment), texts(moment)
            assert "96x64, reduced from 192x128 (x0.50)" in texts(moment)[0]
    asyncio.run(scenario())


def make_wide(home):
    video = home / "wide.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1600x900:rate=5:d=1", "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(video))
    brief = base_brief(home)
    brief["evidence"]["sourcePath"] = str(video)
    brief["evidence"]["capture"] = {"widthPx": 1600, "heightPx": 900, "deviceScale": None, "imageMaxSize": 1280}
    write_active(home, brief)


def png_size(content):
    import base64
    data = base64.b64decode(content.data)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_read_moment_crop_and_max_size(server, home):
    make_wide(home)

    async def scenario():
        async with connect(server, home) as client:
            crop = await client.call_tool("anypoach_read_moment", {"timeMs": 0, "crop": {"x": 100, "y": 50, "width": 400, "height": 300}})
            assert not is_error(crop), texts(crop)
            assert png_size(images(crop)[0]) == (400, 300)
            assert "crop 100,50 400x300 of 1600x900, native size" in texts(crop)[0]
            small = await client.call_tool("anypoach_read_moment", {"timeMs": 0, "maxSize": 640})
            assert png_size(images(small)[0]) == (640, 360)
            assert "640x360, reduced from 1600x900 (x0.40)" in texts(small)[0]
            default = await client.call_tool("anypoach_read_moment", {"timeMs": 0})
            assert png_size(images(default)[0]) == (1280, 720)
    asyncio.run(scenario())


def test_read_moment_reports_a_bad_crop(server, home):
    make_wide(home)

    async def scenario():
        async with connect(server, home) as client:
            outside = await client.call_tool("anypoach_read_moment", {"timeMs": 0, "crop": {"x": 1500, "y": 0, "width": 200, "height": 100}})
            assert is_error(outside) and "Crop must fit inside the 1600x900 frame" in texts(outside)[0]
            tiny = await client.call_tool("anypoach_read_moment", {"timeMs": 0, "maxSize": 8})
            assert is_error(tiny)
    asyncio.run(scenario())


def test_an_oversized_image_is_refused_with_a_hint(monkeypatch):
    from anypoach.mcp import server as mcp_server
    mcp_server.ensure_png_fits(b"x" * 1000)
    monkeypatch.setattr(mcp_server, "FIVE_MB", 1000)
    with pytest.raises(ValueError, match="use a smaller crop or maxSize"):
        mcp_server.ensure_png_fits(b"x" * 1001)
