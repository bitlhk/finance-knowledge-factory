import hashlib
import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from web_preview.server import ROOT, BASELINE_SHA, assets, checked, handler, snapshot


def test_frozen_ui_and_evidence():
    assert hashlib.sha256((ROOT / "web_preview/baseline/v1.5.html").read_bytes()).hexdigest() == BASELINE_SHA
    data = snapshot()
    assert data["liveExecution"] is False
    assert data["publicationAllowed"] is False
    assert len(data["bundles"]) == 4
    assert data["bundles"]["P08-1"]["parts"]["assessment"]["status"] == "SEMANTIC_ERROR"
    results = data["files"]["archive/P43-1-bundle.json"]["results"]
    assert sum(not r["passed"] for r in results) == 6
    assert all(r["executor"] == "INPUT_SCOPE_GUARD" for r in results)
    assert len(assets()) == 3


@pytest.mark.parametrize("mode", ["changed", "missing"])
def test_evidence_never_silently_falls_back(tmp_path, mode):
    folder = tmp_path / "evidence/m1-verified-lowering"
    shutil.copytree(ROOT / "evidence/m1-verified-lowering", folder)
    path = folder / "attempts/P08-1.json"
    if mode == "changed":
        path.write_text("{}")
    else:
        path.unlink()
    with pytest.raises((ValueError, OSError)):
        snapshot(tmp_path)


def test_readonly_http_allowlist_and_fail_closed(tmp_path):
    # Minimal root is deliberately missing evidence; static files alone must not fake success.
    shutil.copytree(ROOT / "web_preview", tmp_path / "web_preview")
    http = ThreadingHTTPServer(("127.0.0.1", 0), handler(tmp_path))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{http.server_port}"
    try:
        with urlopen(base) as response:
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        for path, method, expected in [("/api/snapshot", "GET", 503), ("/api/publish", "POST", 405),
                                       ("/../.git/config", "GET", 404), ("/baseline/v1.5.html", "GET", 404)]:
            with pytest.raises(HTTPError) as exc:
                urlopen(Request(base + path, method=method))
            assert exc.value.code == expected
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
