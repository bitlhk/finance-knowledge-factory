"""Freeze first, then run a bounded serial batch. No tuning, retries or publishing."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from knowledge_core.contracts import Rejected, digest
from knowledge_core.rules import evaluate
from probes.documents.anchor_bridge import build, bind_rule_evidence
from probes.flowable.compiler import compile_rule, prepare
from probes.llm.candidate_bundle import evidence_digest, seal, verify
from probes.llm.coverage import assess_coverage, project
from probes.llm.coverage_gold import GOLD
from probes.llm.coverage_recipe import RECIPE, messages
from probes.llm.linked import decode_envelope
from probes.llm.policy_gold import HOST


ROOT = Path(__file__).parents[2]
RAW_PATH = ROOT / "evidence/m1-round3/sources/regulation.html"


def implementation_identity():
    import hashlib
    files = ["probes/llm/coverage.py", "probes/llm/coverage_gold.py", "probes/llm/coverage_recipe.py",
             "probes/llm/run_coverage.py", "probes/llm/candidate_bundle.py", "probes/llm/linked.py",
             "probes/documents/anchor_bridge.py", "probes/flowable/compiler.py", "knowledge_core/rules.py"]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    raw = RAW_PATH.read_bytes()
    chunks = json.loads((ROOT / "evidence/m1-round2/html-comparison.json").read_text())["results"]["docling"]["chunks"]
    sources = {}
    for key, gold in GOLD.items():
        src, bridge = build(raw, [c for c in chunks if c["clause"] == gold["clause"]], "full-coverage-" + key)
        sources[key] = {"source": src, "bridge": bridge}
    payload = {"schemaVersion": "coverage-experiment.v0.1", "recipe": RECIPE, "gold": GOLD,
               "implementation": implementation_identity(),
               "sourceBytesDigest": __import__("hashlib").sha256(raw).hexdigest(), "sources": sources,
               "parameters": {"model": "deepseek-v4-flash", "temperature": 0.1, "top_p": 1,
                              "max_tokens": 8192, "thinking": {"type": "disabled"}, "stream": False},
               "attempts": [{"id": f"{key}-{repeat}", "case": key, "repeat": repeat}
                            for repeat in (1, 2) for key in GOLD],
               "scope": "FULL_CLAUSE_COVERAGE_AND_BOUNDED_SUBCONDITIONS",
               "goldProvenance": "ENGINEER_AUTHORED_NOT_BUSINESS_OWNER_APPROVED",
               "heldOut": ["P09", "P12"], "heldOutPolicy": "NO_PROMPT_TUNING_AFTER_FIRST_CALL",
               "automaticRetries": 0, "cost": None, "publicationAllowed": False}
    write(output / "frozen.json", payload)
    write(output / "freeze-receipt.json", {"digest": evidence_digest(payload), "createdEpochSeconds": int(time.time())})
    print("Frozen:", output, "attempts:", len(payload["attempts"]), flush=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Rejected("MODEL_REDIRECT_REFUSED")


def run(output):
    frozen = json.loads((output / "frozen.json").read_text())
    receipt = json.loads((output / "freeze-receipt.json").read_text())
    if evidence_digest(frozen) != receipt["digest"]:
        raise Rejected("FREEZE_CHANGED")
    if frozen["recipe"] != RECIPE or frozen["gold"] != GOLD:
        raise Rejected("FROZEN_IMPLEMENTATION_CHANGED")
    if frozen["implementation"] != implementation_identity():
        raise Rejected("FROZEN_IMPLEMENTATION_CHANGED")
    raw = RAW_PATH.read_bytes()
    if __import__("hashlib").sha256(raw).hexdigest() != frozen["sourceBytesDigest"]:
        raise Rejected("FROZEN_SOURCE_CHANGED")
    key, base = os.environ["OPENAI_API_KEY"], os.environ["OPENAI_BASE_URL"].rstrip("/")
    if not key or not base.startswith("https://") or os.environ.get("OPENAI_MODEL") != frozen["parameters"]["model"]:
        raise Rejected("MANAGED_MODEL_CONNECTION_MISMATCH")
    attempts_dir = output / "attempts"
    attempts_dir.mkdir(exist_ok=False)
    opener = urllib.request.build_opener(NoRedirect)
    summaries, models, engine_cases = [], {}, []
    for attempt in frozen["attempts"]:
        case_id = attempt["case"]
        src = frozen["sources"][case_id]["source"]
        bridge = frozen["sources"][case_id]["bridge"]
        payload = {**frozen["parameters"], "messages": messages(frozen["recipe"], src)}
        record = {**attempt, "request": payload, "requestDigest": evidence_digest(payload),
                  "freezeDigest": receipt["digest"], "cost": None, "publicationAllowed": False}
        started = time.monotonic()
        try:
            req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode(),
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with opener.open(req, timeout=180) as response:
                body = response.read(2_000_001).decode()
            if key in body or len(body) > 2_000_000:
                raise Rejected("RESPONSE_UNSAFE_OR_TOO_LARGE")
            data = json.loads(body)
            record.update(response=data, responseModel=data.get("model"), usage=data.get("usage"), modelCall="COMPLETED")
            if data["choices"][0].get("finish_reason") != "stop":
                raise Rejected("MODEL_OUTPUT_NOT_COMPLETE")
            coverage, fmt = decode_envelope(data["choices"][0]["message"]["content"])
            assessment = assess_coverage(coverage, src, frozen["gold"][case_id])
            projection = project(coverage, src, frozen["recipe"]["fields"], frozen["recipe"]["scope"])
            ir = projection["ir"]
            compiled = [compile_rule(ir, r["id"]) for r in ir["rules"]] if ir else []
            checks = []
            for semantic_key, gold_cases in frozen["gold"][case_id]["execution"].items():
                rule_id = assessment["mapping"].get(semantic_key)
                if not ir or rule_id not in {r["id"] for r in ir["rules"]}:
                    checks.append({"semanticKey": semantic_key, "status": "NOT_EXECUTABLE_OR_UNMATCHED"})
                    continue
                model = compile_rule(ir, rule_id)
                models[model["compiledDigest"]] = model
                for index, gold in enumerate(gold_cases):
                    host = {**HOST, **gold.get("host", {})}
                    reference = evaluate(ir, rule_id, gold["inputs"], host)["decision"]
                    test_id = f"{attempt['id']}-{semantic_key}-{index}"
                    checks.append({"id": test_id, "semanticKey": semantic_key, "status": "REFERENCE_EXECUTED",
                                   "expected": gold["expected"], "actual": reference,
                                   "passed": reference == gold["expected"]})
                    engine_cases.append({"id": test_id, "expected": gold["expected"], "reference": reference,
                                         "compiledDigest": model["compiledDigest"],
                                         **prepare(ir, rule_id, gold["inputs"], host, model)})
            parts = {"source": src, "bridge": bridge, "recipe": frozen["recipe"], "request": payload,
                     "response": data, "coverage": coverage, "projection": projection, "assessment": assessment,
                     "gold": frozen["gold"][case_id], "compiled": compiled,
                     "binding": bind_rule_evidence(raw, src, bridge, ir) if ir else None,
                     "execution": {"status": "ENGINE_PENDING", "referenceChecks": checks}}
            manifest = seal(raw, parts)
            verify(raw, parts, manifest)
            record.update(status="ANALYZED", format=fmt, strictJsonCompliant=fmt == "JSON",
                          assessment=assessment, checks=checks)
            write(attempts_dir / (attempt["id"] + "-bundle.json"), {"manifest": manifest, "parts": parts})
        except urllib.error.HTTPError as exc:
            record.update(status="HTTP_FAILED", httpStatus=exc.code)
        except Exception as exc:
            record.update(status="FAILED", errorType=type(exc).__name__)
            if hasattr(exc, "code"):
                record["errorCode"] = exc.code
        record["elapsedMilliseconds"] = round((time.monotonic() - started) * 1000)
        write(attempts_dir / (attempt["id"] + ".json"), record)
        summary = {k: record[k] for k in ("id", "case", "status", "modelCall", "responseModel", "usage", "errorCode", "httpStatus", "strictJsonCompliant") if k in record}
        summary["semanticPassed"] = record.get("assessment", {}).get("passed", False)
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if record.get("httpStatus") in (401, 403, 429):
            break
    write(output / "summary.json", {"attempts": summaries, "planned": len(frozen["attempts"]),
                                     "cost": None, "publicationAllowed": False})
    write(output / "engine-request.json", {"models": list(models.values()), "cases": engine_cases, "faults": []})
    if len(summaries) != len(frozen["attempts"]) or not all(r["semanticPassed"] for r in summaries):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"freeze": freeze, "run": run}[args.action](args.output)
