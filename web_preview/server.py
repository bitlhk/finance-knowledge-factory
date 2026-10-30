"""Loopback-only preview with an immutable, hash-checked evidence allowlist."""
import argparse
import hashlib
import json
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80"
INDEX_SHA = "a67a766f5bfcb86a448b755968fbb38b824e78317aed59cf808cdd4ff1e6988c"
EVIDENCE_COMMIT = "a91add94038d03f6c46aa067135b98b99cd7f85a"


def checked(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("EVIDENCE_DIGEST_MISMATCH: " + path.name)
    return data


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div"} and not self.hidden:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def snapshot(root=ROOT):
    from probes.llm.lowering_bundle import verify

    folder = root / "evidence/m1-verified-lowering"
    index = json.loads(checked(folder / "INDEX.json", INDEX_SHA))
    files = {name: json.loads(checked(folder / name, sha)) for name, sha in index["files"].items()}
    raw = (root / "evidence/m1-round3/sources/regulation.html").read_bytes()
    # Source identity is sealed in every candidate; do not trust a mutable draft.
    bundles = {name.split("/")[-1].removesuffix("-bundle.json"): obj
               for name, obj in files.items() if name.startswith("attempts/") and name.endswith("-bundle.json")}
    for obj in bundles.values():
        verify(raw, obj["parts"], obj["manifest"])
    parser = PlainText()
    parser.feed(raw.decode("utf-8"))
    return {"mode": "HISTORICAL_REAL_EVIDENCE", "publicationAllowed": False,
            "liveExecution": False, "evidenceCommit": EVIDENCE_COMMIT,
            "prototypeSha256": BASELINE_SHA, "indexSha256": INDEX_SHA,
            "sourceSha256": hashlib.sha256(raw).hexdigest(),
            "originalText": "".join(parser.chunks), "files": files, "bundles": bundles,
            "fileDigests": index["files"]}


def assets(root=ROOT):
    original = checked(root / "web_preview/baseline/v1.5.html", BASELINE_SHA).decode()
    css = original.split("<style>", 1)[1].split("</style>", 1)[0]
    return {"/": ("text/html; charset=utf-8", (root / "web_preview/index.html").read_bytes()),
            "/app.js": ("text/javascript; charset=utf-8", (root / "web_preview/app.js").read_bytes()),
            "/style.css": ("text/css; charset=utf-8", (css + (root / "web_preview/preview.css").read_text()).encode())}


def handler(root=ROOT):
    static = assets(root)

    class ReadOnly(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            status = 200
            if path == "/api/snapshot":
                mime = "application/json"
                try:
                    data = json.dumps(snapshot(root), ensure_ascii=False).encode()
                except Exception:
                    status, data = 503, b'{"error":"EVIDENCE_UNAVAILABLE_OR_CHANGED"}'
            elif path in static:
                mime, data = static[path]
            else:
                mime, status, data = "text/plain", 404, b"Not found"
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.send_error(405, "Read-only preview")

        do_PUT = do_DELETE = do_PATCH = do_POST

    return ReadOnly


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--port", type=int, default=61351)
    args = cli.parse_args()
    snapshot()  # Fail before listening if fixed evidence is incomplete.
    ThreadingHTTPServer(("127.0.0.1", args.port), handler()).serve_forever()
