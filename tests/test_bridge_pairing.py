"""The Chrome pairing code: created once, owner-only, replaceable."""
import re
import sys

import pytest

from anypoach.bridge import pairing

UUID = re.compile(r"[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}")


def test_a_code_is_created_once_and_reused(tmp_path):
    first = pairing.load_or_create(tmp_path)
    assert UUID.fullmatch(first) and pairing.load_or_create(tmp_path) == first


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_code_file_is_owner_only(tmp_path):
    pairing.load_or_create(tmp_path)
    assert (tmp_path / "bridge-pairing").stat().st_mode & 0o777 == 0o600


def test_a_malformed_file_is_replaced(tmp_path):
    (tmp_path / "bridge-pairing").write_text("not a code")
    assert UUID.fullmatch(pairing.load_or_create(tmp_path))


def test_rotate_replaces_the_code(tmp_path):
    old = pairing.load_or_create(tmp_path)
    new = pairing.rotate(tmp_path)
    assert new != old and pairing.load_or_create(tmp_path) == new
