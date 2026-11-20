import json
import os
import re
import sys
import uuid

import pytest

from poach.analysis.motion import MotionTiming
from poach.analysis.types import InspectionResult, Keyframe
from poach.brief.cleanup import clear_storage, scan_storage
from poach.brief.store import read_brief, share

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
UUID = "[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"


def result(media, name="capture"):
    frame = media.parent / f"{name}-start-0ms.png"
    frame.write_bytes(b"png")
    return InspectionResult("video", str(media), 0, [Keyframe("start", 0, str(frame), 0.0)], ["#000000"],
                            MotionTiming(0, None, "No measurable motion in sampled frames"))


@pytest.fixture
def env(tmp_path):
    cache, temp = tmp_path / "cache", tmp_path / "tmp"
    (temp / "Poach").mkdir(parents=True)
    return cache, temp


def make_media(temp, name="capture-%s.mov"):
    path = temp / "Poach" / (name % str(uuid.uuid4()).upper())
    path.write_bytes(b"x" * 10)
    return path


def age(cache, brief_id, seconds):
    for path in (cache / "briefs" / f"{brief_id.lower()}.json", cache / "active-brief.json"):
        data = json.loads(path.read_text())
        if data["briefId"] == brief_id:
            data["sharedAt"] -= seconds
            path.write_text(json.dumps(data))


def test_share_writes_the_v1_brief_without_keyframe_motion(env):
    cache, temp = env
    brief_id = share(result(make_media(temp)), "ctx", [{"timeMs": 5, "text": "note"}], cache=cache)
    assert re.fullmatch(UUID, brief_id)
    brief = json.loads((cache / "active-brief.json").read_text())
    assert (brief["version"], brief["briefId"], brief["context"]) == (1, brief_id, "ctx")
    assert "Inspect the keyframes" in brief["instruction"]
    assert set(brief["evidence"]["keyframes"][0]) == {"kind", "timeMs", "imagePath"}
    assert brief["evidence"]["annotations"] == [{"timeMs": 5, "text": "note"}]
    assert (cache / "briefs" / f"{brief_id.lower()}.json").read_text() == (cache / "active-brief.json").read_text()


@posix_only
def test_cache_is_user_only(env):
    cache, temp = env
    brief_id = share(result(make_media(temp)), "", [], cache=cache)
    modes = {p: os.stat(p).st_mode & 0o777 for p in (cache, cache / "briefs", cache / "active-brief.json",
                                                     cache / "briefs" / f"{brief_id.lower()}.json")}
    assert list(modes.values()) == [0o700, 0o700, 0o600, 0o600]


def test_archived_briefs_remain_readable_by_id_after_a_newer_share(env):
    cache, temp = env
    first = share(result(make_media(temp)), "first", [], cache=cache)
    second = share(result(make_media(temp)), "second", [], cache=cache)
    assert read_brief(first, cache=cache)["context"] == "first"
    assert read_brief(None, cache=cache)["briefId"] == second
    assert read_brief(first.lower(), cache=cache)["briefId"] == first


@pytest.mark.parametrize("bad", ["../x", "not-a-uuid", "..\\..\\x", ""])
def test_brief_id_must_be_a_uuid(env, bad):
    with pytest.raises(ValueError, match="UUID"):
        read_brief(bad or "  ", cache=env[0])


def test_unknown_id_after_replacement_asks_to_share_again(env):
    cache, temp = env
    share(result(make_media(temp)), "", [], cache=cache)
    with pytest.raises(ValueError, match="replaced or its local archive is unavailable"):
        read_brief(str(uuid.uuid4()).upper(), cache=cache)


def test_expired_brief_is_rejected_and_its_archive_removed(env):
    cache, temp = env
    first = share(result(make_media(temp)), "", [], cache=cache)
    second = share(result(make_media(temp)), "", [], cache=cache)
    age(cache, first, 86_401)
    with pytest.raises(ValueError, match="expired"):
        read_brief(first, cache=cache)
    assert not (cache / "briefs" / f"{first.lower()}.json").exists()
    assert read_brief(second, cache=cache)["briefId"] == second
    age(cache, second, 86_401)
    with pytest.raises(ValueError, match="expired"):
        read_brief(None, cache=cache)
    assert (cache / "active-brief.json").exists()  # only the app replaces the latest snapshot


@posix_only
def test_symlinked_cache_entries_are_refused(env):
    cache, temp = env
    share(result(make_media(temp)), "", [], cache=cache)
    target = cache / "elsewhere.json"
    (cache / "active-brief.json").rename(target)
    (cache / "active-brief.json").symlink_to(target)
    with pytest.raises(ValueError, match="regular file"):
        read_brief(None, cache=cache)
    with pytest.raises(ValueError, match="regular file"):
        scan_storage(temp=temp, cache=cache)


def test_scan_protects_media_of_valid_briefs_and_lists_the_rest(env):
    cache, temp = env
    kept = make_media(temp)
    share(result(kept), "", [], cache=cache)
    stale = make_media(temp)
    (temp / "Poach" / "notes.txt").write_text("not ours")
    folder = temp / "poach-AbC123"
    folder.mkdir()
    (folder / "clip-start-12ms.png").write_bytes(b"12345")
    (folder / "unrelated.png").write_bytes(b"x")
    usage = scan_storage(temp=temp, cache=cache)
    assert sorted(p.name for p in usage.removable) == sorted([stale.name, "clip-start-12ms.png"])
    assert (usage.total, usage.unused) == (25, 15)  # kept 10 + stale 10 + frame 5; the stale pair is unused


def test_media_of_expired_briefs_and_open_paths(env):
    cache, temp = env
    old, opened = make_media(temp), make_media(temp)
    brief_id = share(result(old), "", [], cache=cache)
    age(cache, brief_id, 86_401)
    assert opened in scan_storage(temp=temp, cache=cache).removable
    names = {p.name for p in scan_storage(temp=temp, cache=cache, open_paths=[str(opened)]).removable}
    assert names == {old.name}


def test_paths_with_spaces_and_accents_are_protected(env):
    cache, temp = env
    folder = temp / "poach-recording-aB3dE9"
    folder.mkdir()
    media = folder / "recording.mp4"
    media.write_bytes(b"x")
    share(result(media, "gravação final"), "", [], cache=cache)
    assert scan_storage(temp=temp, cache=cache).removable == []


@posix_only
def test_symlinked_temp_dirs_and_files_are_ignored(env):
    cache, temp = env
    outside = temp / "outside"
    outside.mkdir()
    (outside / "recording.mp4").write_bytes(b"x")
    (temp / "poach-recording-Zz9Zz9").symlink_to(outside)
    (temp / "Poach" / f"capture-{uuid.uuid4()}.mov").symlink_to(outside / "recording.mp4")
    assert scan_storage(temp=temp, cache=cache).removable == []


def test_clear_removes_unused_media_and_empty_folders_only(env):
    cache, temp = env
    kept = make_media(temp)
    share(result(kept), "", [], cache=cache)
    stale = make_media(temp)
    folder = temp / "poach-AbC123"
    folder.mkdir()
    (folder / "clip-image.png").write_bytes(b"x")
    clear_storage(temp=temp, cache=cache)
    assert kept.exists() and not stale.exists() and not folder.exists() and (temp / "Poach").exists()


def test_malformed_briefs_stop_the_scan_instead_of_risking_media(env):
    cache, temp = env
    cache.mkdir()
    (cache / "active-brief.json").write_text("{not json")
    with pytest.raises(ValueError, match="unreadable"):
        scan_storage(temp=temp, cache=cache)


def test_missing_cache_is_an_empty_scan(env):
    assert scan_storage(temp=env[1], cache=env[0] / "nope").total == 0
