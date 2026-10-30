"""Replayable M1 evidence binding for semantic extraction and verified lowering."""
from knowledge_core.contracts import Rejected, digest
from probes.documents.anchor_bridge import verify_bridge, bind_rule_evidence
from probes.flowable.compiler import compile_rule
from probes.llm.candidate_bundle import seal as old_seal
from probes.llm.coverage_recipe import messages
from probes.llm.coverage_gold_v2 import GOLD
from probes.llm.coverage_review_v2 import assess
from probes.llm.linked import decode_envelope
from probes.llm.semantic_v2 import RECIPE
from probes.llm.verified_lowering import lower


def seal(raw, parts):
    result = old_seal(raw, parts)
    result["schemaVersion"] = "m1-lowering-evidence.v0.2"
    return result


def verify(raw, parts, manifest):
    if manifest != seal(raw, parts):
        raise Rejected("BUNDLE_DIGEST_MISMATCH")
    if parts["recipe"] != RECIPE or parts["gold"] not in GOLD.values():
        raise Rejected("UNFROZEN_RECIPE_OR_GOLD")
    verify_bridge(raw, parts["source"], parts["bridge"], digest(parts["bridge"]))
    if parts["request"]["messages"] != messages(RECIPE, parts["source"]):
        raise Rejected("BUNDLE_REQUEST_MISMATCH")
    decoded, _ = decode_envelope(parts["response"]["choices"][0]["message"]["content"])
    if decoded != parts["coverage"]:
        raise Rejected("BUNDLE_RESPONSE_MISMATCH")
    expected = lower(decoded, parts["source"])
    if expected != parts["projection"]:
        raise Rejected("BUNDLE_LOWERING_MISMATCH")
    if assess(decoded, parts["source"], parts["gold"]) != parts["assessment"]:
        raise Rejected("BUNDLE_ASSESSMENT_MISMATCH")
    ir = expected["ir"]
    compiled = [compile_rule(ir, r["id"]) for r in ir["rules"]] if ir else []
    if compiled != parts["compiled"]:
        raise Rejected("BUNDLE_COMPILED_MISMATCH")
    binding = bind_rule_evidence(raw, parts["source"], parts["bridge"], ir) if ir else None
    if binding != parts["binding"]:
        raise Rejected("BUNDLE_BINDING_MISMATCH")
    return True
