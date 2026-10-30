"""Separate downstream admission check; never overwrites the worker's raw result."""
import argparse
import json
from pathlib import Path
import re

from probes.wiki.worker_probe import sha, write


def assess(body, exported_pages):
    links = set(re.findall(r"\[\[([^\]]+)\]\]", body))
    unknown = sorted(link for link in links if not link.startswith("source:") and link not in exported_pages)
    errors = ["UNRESOLVED_PAGE_REFERENCE"] if unknown else []
    if sum(1 for line in body.splitlines() if line.strip().startswith("```")) % 2:
        errors.append("UNBALANCED_CODE_FENCE")
    return {"adapterVersion": "wiki-handoff-check.v0.1", "errors": errors,
            "unresolvedPages": unknown, "candidateAdmission": "BLOCKED" if errors else "REVIEW_REQUIRED",
            "publicationAllowed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    candidate = json.loads((args.output / "candidate.json").read_text())
    result = {"candidateDigest": sha(candidate), **assess(candidate["body"], [])}
    write(args.output / "handoff.json", result)
    print(json.dumps(result))
