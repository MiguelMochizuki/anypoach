"""The Chrome companion: its manifest, its service worker against the real server, and its capture script in Chrome."""
import functools
import html
import http.server
import json
import re
import shutil
import subprocess
import threading
import tomllib
from pathlib import Path

import pytest

from anypoach.bridge.evidence import EvidenceStore, parse_evidence
from anypoach.bridge.server import BridgeServer
from tests.test_bridge_evidence import START, session

EXTENSION = Path(__file__).resolve().parent.parent / "src/anypoach/chrome_extension"
CHROME_DIR = Path(__file__).resolve().parent / "chrome"
CODE = "0123ABCD-0000-4000-8000-0123456789AB"


def extension_files():
    return [p for p in EXTENSION.iterdir() if p.is_file()]


def test_manifest_is_minimal_and_ours():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3 and manifest["name"] == "AnyPoach"
    assert manifest["host_permissions"] == ["http://127.0.0.1/*"]
    assert "<all_urls>" not in json.dumps(manifest)
    assert sorted(manifest["permissions"]) == ["activeTab", "scripting", "storage"]
    assert manifest["background"]["service_worker"] == "bridge.js"
    referenced = [manifest["action"]["default_popup"], manifest["background"]["service_worker"],
                  *manifest["icons"].values(), *manifest["action"]["default_icon"].values()]
    assert all((EXTENSION / name).is_file() for name in referenced)
    assert (EXTENSION / "capture.js").is_file()


def test_extension_version_matches_the_package():
    project = tomllib.loads((EXTENSION.parent.parent.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert manifest == project, "bump pyproject.toml and the manifest together"


def test_adapted_files_carry_the_license_notice_and_nothing_else_names_the_original():
    notice = "Adapted from the Poach Chrome extension (Apache-2.0) and changed for AnyPoach. See NOTICE."
    for path in extension_files():
        if path.suffix in {".js", ".html", ".css"}:
            text = path.read_text(encoding="utf-8")
            assert notice in text.splitlines()[0] + (text.splitlines()[1] if path.suffix == ".html" else ""), path.name
            assert not re.search(r"(?<![A-Za-z])Poach(?![A-Za-z])", text.replace(notice, "")), path.name
            assert "47831" not in text


def test_the_wheel_ships_the_extension(tmp_path):
    if shutil.which("uv") is None:
        pytest.skip("uv is needed to build the wheel")
    root = Path(__file__).resolve().parent.parent
    subprocess.run(["uv", "build", "--wheel", "-o", str(tmp_path)], cwd=root, check=True, capture_output=True)
    import zipfile
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    for name in ("manifest.json", "bridge.js", "capture.js", "popup.html", "popup.js", "icon.png"):
        assert f"anypoach/chrome_extension/{name}" in names


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed to run the service worker")
def test_bridge_flow_against_the_real_server(tmp_path):
    store = EvidenceStore()
    server = BridgeServer(store, CODE, port=0)
    server.start()
    try:
        sample = tmp_path / "session.json"
        sample.write_text(json.dumps(session()), encoding="utf-8")
        done = subprocess.run(["node", str(CHROME_DIR / "bridge_flow.mjs"), str(server.port), CODE, str(sample),
                               str(EXTENSION / "bridge.js")], capture_output=True, text=True, timeout=60, check=False)
        assert done.returncode == 0, done.stderr
        out = json.loads(done.stdout)
        assert "Pair again" in out["afterOneDrop"]["error"]  # the retry reached the server and got its 401
        assert out["afterTwoDrops"] == {"error": "Open AnyPoach and try again."}
        assert "error" in out["wrongCode"] and "Pair again" in out["wrongCode"]["error"]
        assert "error" in out["malformedCode"]
        assert out["rightCode"] == {"ok": True} and out["storedAfterPairing"] is True
        assert out["capture"] == {"ok": True}
        assert "exceeds" in out["oversized"]["error"]
        assert out["droppedComponentsAtEnd"] == {"ok": True}
        assert "componentsAtEnd" not in store.latest_for((START, START + 1000))
        assert "Pair again" in out["changedCode"]["error"]
        assert "foreignMessage" not in out
        assert store.latest_for((START, START + 1000))["origin"] == "https://example.com"
    finally:
        server.stop()


def find_chrome():
    return next((found for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")
                 if (found := shutil.which(name))), None)


def run_capture_page(tmp_path, page, fragment=""):
    """Serve a test page next to a copy of capture.js with a test-only hook, load it in headless Chrome, and return the
    JSON the page writes into `#out`. The hook exists because a page cannot press Enter on a trusted keydown."""
    source = (EXTENSION / "capture.js").read_text(encoding="utf-8")
    assert source.rstrip().endswith("})();")
    hook = source.rstrip()[: -len("})();")] + "  globalThis.__anypoachTest = { start, select, endSelection, measureComponents, cardModel, placeCard, showCard };\n})();\n"
    (tmp_path / "capture.js").write_text(hook, encoding="utf-8")
    shutil.copy(CHROME_DIR / page, tmp_path / "index.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html{fragment}"
        done = subprocess.run([find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000",
                               f"--user-data-dir={tmp_path / 'profile'}", "--dump-dom", url],
                              capture_output=True, text=True, timeout=90, check=False)
        match = re.search(r'<pre id="out">(.*?)</pre>', done.stdout, re.DOTALL)
        assert match and match.group(1).strip(), done.stderr[-500:]
        return json.loads(html.unescape(match.group(1)))
    finally:
        httpd.shutdown()


needs_chrome = pytest.mark.skipif(find_chrome() is None, reason="Chrome is needed to run the capture script")


@needs_chrome
def test_capture_script_records_a_component_in_headless_chrome(tmp_path):
    payload = run_capture_page(tmp_path, "capture_page.html")
    evidence = payload["evidence"]
    assert evidence["version"] == 1 and evidence["origin"].startswith("http://127.0.0.1:")
    widths = [state["rect"][2] for state in evidence["states"]]
    assert widths[-1] > widths[0] and widths[-1] == pytest.approx(220, abs=1)
    assert len(evidence["states"]) == 2, "scrolling the page is not a change of the component"
    assert all(state["pageRect"][2:] == state["rect"][2:] for state in evidence["states"])
    animation = evidence["animations"][0]
    assert animation["durationMs"] == 300 and animation["easing"] == "ease-out" and animation["keyframes"]
    assert evidence["devicePixelRatio"] > 0 and evidence["viewport"]["width"] > 0
    assert payload["streamed"] >= 1
    assert parse_evidence(evidence)["states"], "the server must accept what the script produces"


@needs_chrome
def test_components_are_measured_relative_to_the_root(tmp_path):
    payload = run_capture_page(tmp_path, "components_page.html")
    components, evidence = payload["components"], payload["evidence"]
    by_text = {c["text"]: c for c in components}
    assert by_text["Title"]["styles"]["fontSize"] == "24px" and by_text["Title"]["parent"] == -1
    card = next(c for c in components if c["rect"][2:] == [180, 100])
    assert card["rect"][0] == 10 and card["parent"] == -1
    assert by_text["Card A"]["parent"] == components.index(card)
    for hidden in ("hidden text", "aria text", "zero text"):
        assert hidden not in by_text
    assert all(c["target"]["tag"] != "input" for c in components)
    assert all(len(c["text"]) <= 80 and c["id"] == i and c["parent"] < i for i, c in enumerate(components))
    assert evidence["components"] == components and evidence["componentsAtEnd"]
    assert parse_evidence(evidence)["components"], "the server must accept what the script produces"


@needs_chrome
def test_more_than_forty_descendants_keep_the_largest_in_document_order(tmp_path):
    components = run_capture_page(tmp_path, "components_page.html", "#many")["components"]
    texts = [c["text"] for c in components]
    assert len(components) == 40 and [c["id"] for c in components] == list(range(40))
    assert texts[:6] == ["d1", "d2", "d3", "d4", "d5", "d6"] and "d7" not in texts and "d8" not in texts
    assert texts[6:] == [f"n{i}" for i in range(26, 60)], "the 34 largest small boxes, in document order"
    assert [c["parent"] for c in components[:6]] == [-1, 0, 1, 2, 3, 4]


@needs_chrome
def test_a_detached_root_measures_nothing(tmp_path):
    assert run_capture_page(tmp_path, "components_page.html", "#detached")["components"] == []


@needs_chrome
def test_card_model_reports_measurements_and_never_the_text(tmp_path):
    models = run_capture_page(tmp_path, "inspector_page.html")["models"]
    plain, tint, fade = models["plain"], models["tint"], models["fade"]
    assert plain["name"] == "div.stage" and plain["size"] == "302 × 122"
    assert plain["font"] == "Arial · 24/28 · 500"
    colors = {c["label"]: c["hex"] for c in plain["colors"]}
    assert colors == {"Text": "#2025C8", "Background": None, "Border": "#888888"}, "a transparent background has no hex"
    assert "radius 12px" in plain["extras"]
    assert "Secret" not in json.dumps(models), "element text must never reach the card"
    assert {c["label"]: c["hex"] for c in tint["colors"]}["Background"] == "#FF633B80"
    assert "opacity 0.3" in tint["extras"] and any(item.startswith("transform") for item in tint["extras"])
    assert fade["animations"] == ["300ms cubic-bezier(0.4, 0, 0.2, 1)"]


@needs_chrome
def test_the_card_is_placed_inside_the_viewport(tmp_path):
    places = run_capture_page(tmp_path, "inspector_page.html")["placements"]
    assert places["roomy"][0] == 212, "right of the target with a 12 px gap"
    assert places["edge"][0] == 1428, "no room on the right, so on the left"
    assert places["bottom"][1] == 752, "pushed up so the bottom stays 8 px inside the viewport"
    assert places["tiny"] == [8, 8], "a viewport smaller than the card clamps to the 8 px margin"
    for left, top in (places["roomy"], places["edge"], places["bottom"]):
        assert left >= 0 and top >= 0 and left + 260 <= 1854 and top + 200 <= 960


@needs_chrome
def test_one_card_exists_while_choosing_and_none_after(tmp_path):
    out = run_capture_page(tmp_path, "inspector_page.html")
    assert out["shown"] == 1 and out["after"] == 0
    assert out["closed"] is True, "the page must not be able to reach into the card"
    assert out["insideViewport"] is True


@needs_chrome
def test_nothing_typed_into_an_editable_area_is_measured(tmp_path):
    payload = run_capture_page(tmp_path, "components_page.html", "#editable")
    assert payload["components"] == [] and payload["evidence"]["components"] == [] and payload["evidence"]["componentsAtEnd"] == []
    assert "typed" not in json.dumps(payload), "text typed by the user must never reach the evidence"


@needs_chrome
def test_modern_css_colors_are_shown_as_colors_not_as_transparent(tmp_path):
    modern = run_capture_page(tmp_path, "inspector_page.html")["models"]["modern"]
    colors = {c["label"]: c["hex"] for c in modern["colors"]}
    assert re.fullmatch(r"#[0-9A-F]{6}", colors["Text"]) and re.fullmatch(r"#[0-9A-F]{6}", colors["Background"]), colors
