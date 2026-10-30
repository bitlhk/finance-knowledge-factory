"""Offline review and numeric-proof probe, separate from governed candidate execution.

The numeric proof cannot clear dependencies or authorize publication of the
original candidate. Its input is the existing verified template receipt only.
"""
import argparse
import hashlib
import json
from pathlib import Path

from knowledge_core.contracts import Rejected
from knowledge_core.rules import evaluate
from probes.flowable.compiler import compile_rule, prepare
from probes.llm.candidate_bundle import evidence_digest
from probes.llm.coverage_review_addendum import review
from probes.llm.linked import convert
from probes.llm.lowering_bundle import verify
from probes.llm.policy_gold import HOST
from probes.llm.run_coverage import RAW_PATH, write
from probes.llm.verified_lowering import FIELDS, SCOPE, recognize


def generate(output):
    destination = output / "addendum"
    destination.mkdir(exist_ok=False)
    rows, cases, models, proofs = [], [], {}, []
    for path in sorted((output / "attempts").glob("*-bundle.json")):
        bundle = json.loads(path.read_text())
        p = bundle["parts"]
        verify(RAW_PATH.read_bytes(), p, bundle["manifest"])
        attempt = path.name.removesuffix("-bundle.json")
        rows.append({"attemptId": attempt, "originalBundleDigest": evidence_digest(bundle),
                     "frozenStatus": p["assessment"]["status"],
                     "addendum": review(p["coverage"], p["source"], p["gold"])})
        for decision in p["projection"]["decisions"]:
            # Only an unconditional numeric expression template is isolated.
            # No general/exception/external context is dropped to get a passing proof.
            if decision["status"] != "VERIFIED_NUMERIC" or decision["unresolvedQuotes"]:
                continue
            proof = recognize(decision["quote"], p["source"])
            if any(proof[k] != decision[k] for k in ("template", "predicate", "appliesWhen")):
                raise Rejected("TEMPLATE_PROOF_CHANGED")
            semantic_keys = [k for k, v in p["assessment"]["mapping"].items() if v == decision["unitId"]]
            if len(semantic_keys) != 1:
                continue
            key = semantic_keys[0]
            tests = p["gold"]["execution"].get(key, [])
            if not tests:
                continue
            # This is a newly identified diagnostic artifact, never the governed rule.
            ir = convert({"rules": [{"id": "numeric-proof", "title": "Template numeric proof only",
                "predicate": proof["predicate"], "appliesWhen": proof["appliesWhen"],
                "scope": SCOPE, "quotes": [decision["quote"]], "exceptions": [], "unresolvedQuotes": []}]},
                p["source"], FIELDS, SCOPE)
            ir["id"] += "-numeric-proof"
            model = compile_rule(ir, "numeric-proof")
            models[model["compiledDigest"]] = model
            proof_id = attempt + "-numeric-proof"
            own_cases = []
            for index, test in enumerate(tests):
                host = {**HOST, **test.get("host", {})}
                own_cases.append({"id": proof_id + "-" + str(index), "expected": test["expected"],
                    "reference": evaluate(ir, "numeric-proof", test["inputs"], host)["decision"],
                    "compiledDigest": model["compiledDigest"], **prepare(ir, "numeric-proof", test["inputs"], host, model)})
            cases.extend(own_cases)
            proofs.append({"id": proof_id, "originalBundleDigest": evidence_digest(bundle),
                "sourceBytesDigest": hashlib.sha256(RAW_PATH.read_bytes()).hexdigest(),
                "source": p["source"], "bridge": p["bridge"], "unitId": decision["unitId"],
                "templateProof": proof, "ir": ir, "compiled": model, "cases": own_cases,
                "originalGovernedProjectionDigest": evidence_digest(p["projection"]),
                "originalDependenciesUnchanged": True, "purpose": "TEMPLATE_NUMERIC_SEMANTICS_ONLY",
                "wholeClauseDecision": "REVIEW_REQUIRED", "publicationAllowed": False})
    write(destination / "review.json", {"rows": rows, "originalResultsUnchanged": True, "newModelCalls": 0})
    write(destination / "numeric-proofs.json", {"proofs": proofs, "notGovernedCandidateAcceptance": True})
    write(destination / "engine-request.json", {"models": list(models.values()), "cases": cases, "faults": []})
    print("Numeric proof cases:", len(cases), "(not governed candidate acceptance)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
