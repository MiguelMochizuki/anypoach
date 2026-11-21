"""Favorites: saving, listing, handoff rebuilding, and refusing hostile `.anypoach` files."""
import base64
import json
import os
import sys

import pytest

from anypoach import favorites
from anypoach.favorites import FavoriteError, FavoriteStore
from anypoach.pointer.trace import Rect
from tests.test_ui_controller import make


@pytest.fixture
def shot(tmp_path):
    controller = make(tmp_path)
    controller.choose_region(Rect(10, 10, 160, 90))
    return controller.screenshot()


@pytest.fixture
def store(tmp_path):
    return FavoriteStore(tmp_path / "data")


def saved(store, shot, name="Hover card"):
    notes = [{"timeMs": 200, "text": "easing"}, {"timeMs": 50, "text": "start"}]
    return store.save(name, shot, "Ease it out.", notes, ["#AABBCC", "#112233"])


def test_a_saved_favorite_comes_back_as_a_handoff(store, shot, tmp_path):
    favorite_id = saved(store, shot)
    assert [s.name for s in store.list()] == ["Hover card"] and store.cover(favorite_id).startswith(b"\x89PNG")
    result, context, notes = store.to_result(favorite_id, tmp_path / "frames")
    assert context == "Ease it out." and result.palette == ["#aabbcc", "#112233"] and result.source_path == ""
    assert [n["text"] for n in notes] == ["easing", "start"] and result.capture.width_px == shot.capture.width_px
    assert all(os.path.isfile(k.image_path) for k in result.keyframes)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_files_are_private_to_the_user(store, shot):
    saved(store, shot)
    assert oct(store._root.stat().st_mode & 0o777) == "0o700"
    assert all(oct(f.stat().st_mode & 0o777) == "0o600" for f in store._root.iterdir())


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_a_bad_name_is_refused(store, shot, name):
    with pytest.raises(FavoriteError):
        store.save(name, shot, "", [], [])
    assert store.list() == []


def test_export_then_import_makes_an_independent_copy(store, shot, tmp_path):
    favorite_id = saved(store, shot)
    out = tmp_path / "share.anypoach"
    store.export(favorite_id, out)
    new_id = FavoriteStore(tmp_path / "other").import_file(out)
    other = FavoriteStore(tmp_path / "other")
    assert new_id != favorite_id and other.list()[0].name == "Hover card"
    assert other.to_result(new_id, tmp_path / "f2")[1] == "Ease it out."


def raw_of(store, shot):
    return json.loads(store._path(saved(store, shot)).read_text())


def write(tmp_path, data):
    path = tmp_path / "bad.anypoach"
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    return path


def mutations(record):
    frame = record["frames"][0]
    yield "not json", b"{nope"
    yield "extra key", {**record, "evil": 1}
    yield "wrong version", {**record, "version": 2}
    yield "bad color", {**record, "palette": ["red"]}
    yield "13 colors", {**record, "palette": ["#000000"] * 13}
    yield "empty note", {**record, "notes": [{"timeMs": 1, "text": ""}]}
    yield "51 notes", {**record, "notes": [{"timeMs": 1, "text": "x"}] * 51}
    yield "no frames", {**record, "frames": []}
    yield "4 frames", {**record, "frames": [frame] * 4}
    yield "bad base64", {**record, "frames": [{**frame, "png": "!!!"}]}
    yield "not a png", {**record, "frames": [{**frame, "png": base64.b64encode(b"GIF89a").decode()}]}
    yield "big png", {**record, "frames": [{**frame, "png": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 300_000).decode()}]}
    yield "huge trace", {**record, "pointerTrace": {"events": ["x" * 1000] * 400}}
    yield "oversize file", b" " * (favorites.FILE_LIMIT + 1)


def test_hostile_files_are_refused_and_nothing_is_stored(store, shot, tmp_path):
    record = raw_of(store, shot)
    target = FavoriteStore(tmp_path / "target")
    for label, data in mutations(record):
        with pytest.raises(FavoriteError):
            target.import_file(write(tmp_path, data))
        assert target.list() == [], label


def test_ids_cannot_escape_the_folder_and_unknown_ones_are_errors(store):
    for bad in ("../secret", "abc", ""):
        with pytest.raises(FavoriteError):
            store.cover(bad)
    store.delete("00000000-0000-0000-0000-000000000000")
    with pytest.raises(FavoriteError):
        store.cover("00000000-0000-0000-0000-000000000000")


def test_list_skips_files_that_do_not_parse_and_delete_removes(store, shot):
    favorite_id = saved(store, shot)
    (store._root / "junk.anypoach").write_text("{}")
    assert [s.id for s in store.list()] == [favorite_id]
    store.delete(favorite_id)
    assert store.list() == []
