"""Local CPU embedding adapter for the isolated RAGFlow network, not a mock."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import time


def main():
    from fastembed import TextEmbedding
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=19382)
    ap.add_argument("--credentials", type=Path, default=Path('.m1-local/ragflow-service/local-credentials.json'))
    ap.add_argument("--state", type=Path, default=Path('.m1-local/ragflow-service'))
    ap.add_argument("--cache", type=Path, default=Path('.m1-local/embedding-model'))
    args = ap.parse_args()
    root = args.state
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    password = json.loads(args.credentials.read_text())["password"]
    net = json.loads(subprocess.check_output(["docker", "--host=unix:///var/run/docker.sock", "network", "inspect", "kf-m1-ragflow_default"]))[0]
    address = net["IPAM"]["Config"][0]["Gateway"]
    model_name = "BAAI/bge-small-zh-v1.5"
    model = TextEmbedding(model_name, cache_dir=str(args.cache), threads=1, local_files_only=True)
    files = {str(p.relative_to(args.cache)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in args.cache.rglob('*') if p.is_file()}
    (root / "embedding-identity.json").write_text(json.dumps({"model": model_name, "fastembed": "0.7.3", "files": files}, indent=2))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            status, answer = 400, {"error": "invalid input"}
            try:
                if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + password):
                    status, answer = 401, {"error": "unauthorized"}
                elif self.path != "/v1/embeddings":
                    status, answer = 404, {"error": "not found"}
                else:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 1_000_000:
                        raise ValueError()
                    data = json.loads(self.rfile.read(size))
                    texts = data["input"]
                    if isinstance(texts, str): texts = [texts]
                    if data.get("model") != model_name or not isinstance(texts, list) or not 1 <= len(texts) <= 64 or not all(isinstance(t, str) for t in texts):
                        raise ValueError()
                    vectors = list(model.embed(texts))
                    answer = {"object": "list", "model": model_name,
                              "data": [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vectors)]}
                    status = 200
                    with (root / "embedding-calls.jsonl").open("a") as stream:
                        stream.write(json.dumps({"time": time.time(), "inputs": len(texts),
                            "inputDigest": hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest(),
                            "dimensions": 512, "tokens": None}) + "\n")
            except (ValueError, KeyError, TypeError):
                pass
            body = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    print("Embedding ready on isolated Docker bridge only", address, args.port, flush=True)
    HTTPServer((address, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
