"""The on-demand update check, with a fake fetch (no network)."""
import json

import pytest

from anypoach.updates import RELEASES_URL, check_for_update, parse_version


def release(tag, url="https://example.test/r"):
    return lambda _url: json.dumps([{"tag_name": tag, "html_url": url}]).encode()


def test_versions_compare_numerically_not_as_text():
    assert parse_version("v0.10.0") > parse_version("0.9.2") and parse_version("1.0") == (1, 0)
    with pytest.raises(ValueError):
        parse_version("latest")


def test_a_newer_release_is_reported_with_its_page():
    assert check_for_update("0.6.0", release("v0.7.0")) == "AnyPoach v0.7.0 is available (you have 0.6.0): https://example.test/r"


def test_the_same_or_an_older_release_is_up_to_date():
    assert "up to date" in check_for_update("0.6.0", release("v0.6.0"))
    assert "up to date" in check_for_update("0.6.0", release("v0.5.9"))


@pytest.mark.parametrize("fetch", [lambda url: (_ for _ in ()).throw(OSError("offline")), lambda url: b"[]",
                                   lambda url: b"not json", release("nightly")])
def test_failures_are_sentences_not_exceptions(fetch):
    assert check_for_update("0.6.0", fetch).startswith("Could not check for updates")


def test_only_the_releases_list_is_requested():
    seen = []
    check_for_update("0.6.0", lambda url: seen.append(url) or release("v0.6.0")(url))
    assert seen == [RELEASES_URL] and RELEASES_URL.startswith("https://api.github.com/")
