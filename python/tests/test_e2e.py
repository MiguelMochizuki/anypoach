"""Record (scripted pointer + fixture clip) -> analyze -> share -> read back through the MCP server."""
import asyncio
import dataclasses

from anypoach.analysis.inspect import inspect_recording
from anypoach.brief.store import share
from anypoach.pointer.recorder import PointerTraceRecorder
from anypoach.pointer.trace import Rect
from tests.test_mcp_server import connect, images, is_error, structured, texts
from tests.test_pointer_recorder import Clock, Script, at


def test_record_share_and_read_through_mcp(clips, tmp_path):
    clock = Clock()
    recorder = PointerTraceRecorder(Rect(0, 0, 160, 90), Script(at(80, 45), at(80, 45, "left"), at(120, 60, "left"), at(120, 60)), clock=clock)
    assert recorder.start(spawn=False)
    for _ in range(4):
        recorder.poll()
        clock.now += 0.25
    trace = recorder.stop().to_json()

    result = dataclasses.replace(inspect_recording(clips["motion"], output_dir=tmp_path / "frames"), pointer_trace=trace)
    cache = tmp_path / "home/Library/Caches/Poach"
    brief_id = share(result, "Ease the box out.", [{"timeMs": 500, "text": "The box settles here."}], cache=cache)

    async def scenario():
        async with connect("python", tmp_path / "home") as client:
            brief = await client.call_tool("poach_read_brief", {"briefId": brief_id})
            assert not is_error(brief)
            data = structured(brief)
            assert data["briefId"] == brief_id and data["context"] == "Ease the box out."
            assert data["evidence"]["pointerTrace"]["available"] is True
            assert [a["kind"] for a in data["evidence"]["interactionActions"]["actions"]] == ["drag"]
            assert len(images(brief)) >= 1
            moment = await client.call_tool("poach_read_moment", {"timeMs": 500, "briefId": brief_id})
            assert not is_error(moment) and len(images(moment)) == 1
            assert "The box settles here." in texts(moment)[0] and "Pointer trace summary: 4 samples" in texts(moment)[0]

    asyncio.run(scenario())
