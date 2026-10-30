"""Bounded real upstream library probe, not a RAGFlow service deployment."""
import os
import argparse
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
SHA = "ac29b4b29928ca65d3efca19b6cfae3f86069b81"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    args=ap.parse_args()
    source=args.source.resolve(strict=True)
    upstream = ROOT / ".m1-local/ragflow-src"
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if actual != SHA:
        raise SystemExit("UPSTREAM_VERSION_MISMATCH")
    subprocess.run(["git", "diff", "--exit-code"], cwd=upstream, check=True)
    output = ROOT / ".m1-local/ragflow" / uuid.uuid4().hex
    output.mkdir(parents=True)
    entry = upstream / "cmd/knowledge_m1_probe"
    entry.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("ragflow_main.go"), entry / "main.go")
    env = {**os.environ, "CGO_ENABLED": "0", "GOMAXPROCS": "2", "GOMEMLIMIT": "2GiB",
           "GOPATH": str(ROOT / ".m1-local/go-path"), "GOCACHE": str(ROOT / ".m1-local/go-cache"),
           "GOTOOLCHAIN": "local"}
    go = ROOT / ".m1-local/go/bin/go"
    with (output / "build.log").open("w") as log:
        result = subprocess.run([str(go), "build", "-p=2", "-o", str(output / "parser"), "./cmd/knowledge_m1_probe"],
                                cwd=upstream, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    print("Evidence:", output, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    with (output / "response.json").open("w") as out, (output / "run.log").open("w") as log:
        subprocess.run([str(output / "parser"), str(source)], env=env, stdout=out, stderr=log, check=True, timeout=30)


if __name__ == "__main__":
    main()
