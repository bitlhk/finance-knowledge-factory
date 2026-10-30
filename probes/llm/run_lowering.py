"""Four frozen serial calls, no retries. Old evidence and scores are read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from knowledge_core.contracts import Rejected
from knowledge_core.rules import evaluate
from probes.documents.anchor_bridge import build, bind_rule_evidence
from probes.flowable.compiler import compile_rule, prepare
from probes.llm.archive_coverage import verify_engine
from probes.llm.candidate_bundle import evidence_digest
from probes.llm.coverage_recipe import messages
from probes.llm.coverage_gold_v2 import GOLD, PROVENANCE
from probes.llm.coverage_review_v2 import assess
from probes.llm.linked import decode_envelope
from probes.llm.lowering_bundle import seal, verify
from probes.llm.policy_gold import HOST
from probes.llm.run_coverage import ROOT, RAW_PATH, NoRedirect, write
from probes.llm.semantic_v2 import RECIPE
from probes.llm.verified_lowering import CONFIG, inspect_legacy, lower


def identity():
    paths = [*sorted((ROOT / "probes/llm").glob("*.py")),
             *sorted((ROOT / "knowledge_core").glob("*.py")),
             ROOT / "probes/documents/anchor_bridge.py", ROOT / "probes/flowable/compiler.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    raw = RAW_PATH.read_bytes()
    chunks = json.loads((ROOT / "evidence/m1-round2/html-comparison.json").read_text())["results"]["docling"]["chunks"]
    sources = {}
    for key, gold in GOLD.items():
        src, bridge = build(raw, [c for c in chunks if c["clause"] == gold["clause"]], "lowering-" + key)
        sources[key] = {"source": src, "bridge": bridge}
    frozen = {"version": "lowering-experiment.v0.1", "recipe": RECIPE, "gold": GOLD,
        "goldProvenance": PROVENANCE, "loweringConfig": CONFIG, "implementation": identity(),
        "sourceBytesDigest": hashlib.sha256(raw).hexdigest(), "sources": sources,
        "parameters": {"model": "deepseek-v4-flash", "temperature": 0.1, "top_p": 1,
                       "max_tokens": 4096, "thinking": {"type": "disabled"}, "stream": False},
        "attempts": [{"id": key + "-1", "case": key} for key in GOLD],
        "heldOut": ["P13", "P41"], "heldOutPolicy": "NO_TUNING_AFTER_FREEZE_NOT_INDEPENDENT_HUMAN_BLIND_TEST",
        "automaticRetries": 0, "cost": None, "publicationAllowed": False}
    write(output / "frozen.json", frozen)
    write(output / "freeze-receipt.json", {"digest": evidence_digest(frozen), "epoch": int(time.time())})
    print("Frozen 4 calls:", output, flush=True)


def retrospective(output):
    old = ROOT / "evidence/m1-round4"
    frozen = json.loads((old / "frozen.json").read_text())
    rows = []
    for key in ("P43", "P08"):
        for repeat in (1, 2):
            path = old / "attempts" / f"{key}-{repeat}.json"
            record = json.loads(path.read_text())
            coverage, _ = decode_envelope(record["response"]["choices"][0]["message"]["content"])
            # No inferred branch or repaired formula is attributed to the old model.
            converted = {"units": [{"id": u["id"], "kind": u["kind"], "quote": u["quote"],
                "state": "PROPOSED_NUMERIC" if u["state"] == "EXECUTABLE" else u["state"],
                "branchQuote": None} for u in coverage["units"]], "relations": coverage["relations"]}
            src = frozen["sources"][key]["source"]
            rows.append({"id": record["id"], "sourceRecordSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "originalAssessment": record.get("assessment"), "originalError": record.get("errorCode"),
                "v2CoverageReview": assess(converted, src, GOLD[key]),
                "legacyFormulaChecks": [{"unitId": u["id"], **inspect_legacy(u, src)} for u in coverage["units"]],
                "adapterLimit": "Branch quotes absent in v1; not inferred. Not a new model experiment."})
    write(output / "retrospective.json", {"rows": rows, "rescoreOfOldResults": False,
        "originalScoresUnchanged": True, "newModelCalls": 0, "publicationAllowed": False})


def run(output):
    frozen = json.loads((output / "frozen.json").read_text())
    receipt = json.loads((output / "freeze-receipt.json").read_text())
    raw = RAW_PATH.read_bytes()
    if evidence_digest(frozen) != receipt["digest"] or frozen["implementation"] != identity():
        raise Rejected("FROZEN_IMPLEMENTATION_CHANGED")
    if frozen["recipe"] != RECIPE or frozen["gold"] != GOLD or frozen["loweringConfig"] != CONFIG:
        raise Rejected("FROZEN_CONTRACT_CHANGED")
    if hashlib.sha256(raw).hexdigest() != frozen["sourceBytesDigest"]:
        raise Rejected("FROZEN_SOURCE_CHANGED")
    key, base = os.environ["OPENAI_API_KEY"], os.environ["OPENAI_BASE_URL"].rstrip("/")
    if not key or not base.startswith("https://") or os.environ.get("OPENAI_MODEL") != frozen["parameters"]["model"]:
        raise Rejected("MANAGED_MODEL_CONNECTION_MISMATCH")
    destination = output / "attempts"
    destination.mkdir(exist_ok=False)
    rows, cases, models = [], [], {}
    for attempt in frozen["attempts"]:
        src = frozen["sources"][attempt["case"]]["source"]
        bridge = frozen["sources"][attempt["case"]]["bridge"]
        payload = {**frozen["parameters"], "messages": messages(RECIPE, src)}
        record = {**attempt, "request": payload, "requestDigest": evidence_digest(payload),
            "freezeDigest": receipt["digest"], "cost": None, "publicationAllowed": False}
        start = time.monotonic()
        try:
            request = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with urllib.request.build_opener(NoRedirect).open(request, timeout=180) as response:
                body = response.read(2_000_001).decode()
            if key in body or len(body) > 2_000_000:
                raise Rejected("RESPONSE_UNSAFE_OR_TOO_LARGE")
            data = json.loads(body)
            record.update(response=data, responseModel=data.get("model"), usage=data.get("usage"), modelCall="COMPLETED")
            if data["choices"][0].get("finish_reason") != "stop":
                raise Rejected("MODEL_OUTPUT_NOT_COMPLETE")
            semantic, fmt = decode_envelope(data["choices"][0]["message"]["content"])
            gold = GOLD[attempt["case"]]
            review, projection = assess(semantic, src, gold), lower(semantic, src)
            ir = projection["ir"]
            compiled = [compile_rule(ir, r["id"]) for r in ir["rules"]] if ir else []
            own_cases, omissions = [], []
            for semantic_key, tests in gold["execution"].items():
                rule_id = review["mapping"].get(semantic_key)
                if not ir or rule_id not in {r["id"] for r in ir["rules"]}:
                    omissions.append({"key": semantic_key, "status": "NO_VERIFIED_EXECUTABLE_SUBCONDITION"})
                    continue
                model = compile_rule(ir, rule_id)
                models[model["compiledDigest"]] = model
                for index, test in enumerate(tests):
                    host = {**HOST, **test.get("host", {})}
                    own_cases.append({"id": f"{attempt['id']}-{semantic_key}-{index}",
                        "expected": test["expected"], "reference": evaluate(ir, rule_id, test["inputs"], host)["decision"],
                        "compiledDigest": model["compiledDigest"], **prepare(ir, rule_id, test["inputs"], host, model)})
            parts = {"source": src, "bridge": bridge, "recipe": RECIPE, "request": payload, "response": data,
                "coverage": semantic, "projection": projection, "assessment": review, "gold": gold,
                "compiled": compiled, "binding": bind_rule_evidence(raw, src, bridge, ir) if ir else None,
                "execution": {"status": "ENGINE_PENDING", "cases": own_cases, "omissions": omissions}}
            bundle = {"manifest": seal(raw, parts), "parts": parts}
            verify(raw, parts, bundle["manifest"])
            write(destination / (attempt["id"] + "-bundle.json"), bundle)
            cases.extend(own_cases)
            record.update(status="ANALYZED", strictJsonCompliant=fmt == "JSON", assessment=review,
                          loweringDecisions=projection["decisions"], omissions=omissions)
        except urllib.error.HTTPError as exc:
            record.update(status="HTTP_FAILED", httpStatus=exc.code)
        except Exception as exc:
            record.update(status="FAILED", errorType=type(exc).__name__)
            if hasattr(exc, "code"):
                record["errorCode"] = exc.code
        record["elapsedMilliseconds"] = round((time.monotonic() - start) * 1000)
        write(destination / (attempt["id"] + ".json"), record)
        summary = {k: record[k] for k in ("id", "status", "modelCall", "responseModel", "usage", "errorCode", "httpStatus", "strictJsonCompliant") if k in record}
        summary["coverageStatus"] = record.get("assessment", {}).get("status", "NOT_ASSESSED")
        rows.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if record.get("httpStatus") in (401, 403, 429):
            break
    write(output / "summary.json", {"attempts": rows, "planned": 4, "cost": None, "publicationAllowed": False})
    write(output / "engine-request.json", {"models": list(models.values()), "cases": cases, "faults": []})


def archive(output, engine_dir):
    request = json.loads((output / "engine-request.json").read_text())
    if request != json.loads((engine_dir / "request.json").read_text()):
        raise Rejected("ENGINE_REQUEST_NOT_THIS_BATCH")
    response = json.loads((engine_dir / "response.json").read_text())
    rows = verify_engine(request, response)
    destination = output / "archive"
    destination.mkdir(exist_ok=False)
    write(destination / "engine-response.json", response)
    write(destination / "engine-exit.json", json.loads((engine_dir / "exit.json").read_text()))
    write(destination / "receipt.json", {"requestDigest": evidence_digest(request), "responseDigest": evidence_digest(response),
        "engineRunId": engine_dir.name, "buildLogSha256": hashlib.sha256((engine_dir / "build.log").read_bytes()).hexdigest(),
        "publicationAllowed": False})
    for path in sorted((output / "attempts").glob("*-bundle.json")):
        bundle = json.loads(path.read_text())
        verify(RAW_PATH.read_bytes(), bundle["parts"], bundle["manifest"])
        own = bundle["parts"]["execution"]["cases"]
        model_ids = {m["compiledDigest"] for m in bundle["parts"]["compiled"]}
        if any(c["compiledDigest"] not in model_ids for c in own):
            raise Rejected("COMPILED_IDENTITY_MISMATCH")
        write(destination / path.name, {"parentSnapshotDigest": evidence_digest(bundle),
            "engineRunId": engine_dir.name, "cases": own,
            "results": [r for r in rows if r["id"] in {c["id"] for c in own}],
            "batchRequestDigest": evidence_digest(request), "publicationAllowed": False})
    write(output / "INDEX.json", {"files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*.json")) if p.name != "INDEX.json"}, "publicationAllowed": False})
    print("Archived actual engine calls:", response["engineCalls"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "retrospective", "run", "archive"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--engine-dir", type=Path)
    args = parser.parse_args()
    if args.action == "archive":
        if args.engine_dir is None:
            parser.error("--engine-dir required")
        archive(args.output, args.engine_dir)
    else:
        {"freeze": freeze, "retrospective": retrospective, "run": run}[args.action](args.output)
