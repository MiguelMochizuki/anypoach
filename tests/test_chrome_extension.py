"""The Chrome companion: its manifest, its service worker against the real server, and its capture script in Chrome."""
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
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


def test_no_file_speaks_of_the_original_by_name():
    for path in extension_files():
        if path.suffix in {".js", ".html", ".json", ".css"}:
            assert not re.search(r"(?<![A-Za-z])Poach(?![A-Za-z])", path.read_text(encoding="utf-8")), path.name
            assert "47831" not in path.read_text(encoding="utf-8")


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
        assert "error" in out["wrongCode"] and "Pair again" in out["wrongCode"]["error"]
        assert "error" in out["malformedCode"]
        assert out["rightCode"] == {"ok": True} and out["storedAfterPairing"] is True
        assert out["capture"] == {"ok": True}
        assert "exceeds" in out["oversized"]["error"]
        assert "Pair again" in out["changedCode"]["error"]
        assert "foreignMessage" not in out
        assert store.latest_for((START, START + 1000))["origin"] == "https://example.com"
    finally:
        server.stop()


def find_chrome():
    return next((found for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")
                 if (found := shutil.which(name))), None)


@pytest.mark.skipif(find_chrome() is None, reason="Chrome is needed to run the capture script")
def test_capture_script_records_a_component_in_headless_chrome(tmp_path):
    source = (EXTENSION / "capture.js").read_text(encoding="utf-8")
    assert source.rstrip().endswith("})();")
    hook = source.rstrip()[: -len("})();")] + "  globalThis.__anypoachTest = { start };\n})();\n"  # test-only: the page cannot press Enter
    (tmp_path / "capture.js").write_text(hook, encoding="utf-8")
    shutil.copy(CHROME_DIR / "capture_page.html", tmp_path / "index.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *args: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
        done = subprocess.run([find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000",
                               f"--user-data-dir={tmp_path / 'profile'}", "--dump-dom", url],
                              capture_output=True, text=True, timeout=90, check=False)
        match = re.search(r'<pre id="out">(.*?)</pre>', done.stdout, re.DOTALL)
        assert match and match.group(1).strip(), done.stderr[-500:]
        import html
        payload = json.loads(html.unescape(match.group(1)))
    finally:
        httpd.shutdown()
    evidence = payload["evidence"]
    assert evidence["version"] == 1 and evidence["origin"].startswith("http://127.0.0.1:")
    widths = [state["rect"][2] for state in evidence["states"]]
    assert widths[-1] > widths[0] and widths[-1] == pytest.approx(220, abs=1)
    animation = evidence["animations"][0]
    assert animation["durationMs"] == 300 and animation["easing"] == "ease-out" and animation["keyframes"]
    assert evidence["devicePixelRatio"] > 0 and evidence["viewport"]["width"] > 0
    assert payload["streamed"] >= 1
    assert parse_evidence(evidence)["states"], "the server must accept what the script produces"
