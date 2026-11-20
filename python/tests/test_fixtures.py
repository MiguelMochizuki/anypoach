import json
import subprocess

from tests.fixtures import build_all


def probe(path, *args):
    out = subprocess.run(["ffprobe", "-v", "error", *args, "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_build_all_makes_expected_clips(tmp_path):
    clips = build_all(tmp_path)
    assert {"motion", "static", "sparse", "overrun", "image", "unicode name"} <= set(clips)
    assert abs(float(probe(clips["motion"], "-show_entries", "format=duration")["format"]["duration"]) - 2) < 0.1
    sparse = probe(clips["sparse"], "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames")
    assert sparse["streams"][0]["nb_read_frames"] == "3"
    assert float(probe(clips["overrun"], "-show_entries", "format=duration")["format"]["duration"]) > 31
    assert " " in clips["unicode name"].name and any(ord(c) > 127 for c in clips["unicode name"].name)
