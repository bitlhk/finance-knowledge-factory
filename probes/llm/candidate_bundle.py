"""Content-addressed M1 evidence closure, deliberately not a publication Manifest."""
import hashlib
import json

from knowledge_core.contracts import Rejected, digest
from probes.documents.anchor_bridge import verify_bridge, bind_rule_evidence
from probes.flowable.compiler import compile_rule
from probes.llm.coverage import assess_coverage, project
from probes.llm.coverage_recipe import messages
from probes.llm.linked import decode_envelope


REQUIRED = {"source", "bridge", "recipe", "request", "response", "coverage", "projection", "assessment", "compiled", "binding", "execution", "gold"}


def evidence_digest(value):
    # Request sampling parameters/usage can contain finite floats; M0 asset
    # hashing deliberately does not. This separate evidence format changes no M0 contract.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def seal(raw, parts):
    if set(parts) != REQUIRED:
        raise Rejected("BUNDLE_PARTS_MISSING_OR_UNKNOWN")
    return {"schemaVersion": "m1-candidate-evidence.v0.1", "publicationAllowed": False,
            "sourceBytesDigest": hashlib.sha256(raw).hexdigest(),
            "parts": {name: evidence_digest(value) for name, value in sorted(parts.items())}}


def verify(raw, parts, manifest):
    if manifest != seal(raw, parts):
        raise Rejected("BUNDLE_DIGEST_MISMATCH")
    verify_bridge(raw, parts["source"], parts["bridge"], digest(parts["bridge"]))
    projection = parts["projection"]
    if parts["request"]["messages"] != messages(parts["recipe"], parts["source"]):
        raise Rejected("BUNDLE_REQUEST_MISMATCH")
    decoded, _ = decode_envelope(parts["response"]["choices"][0]["message"]["content"])
    if decoded != parts["coverage"]:
        raise Rejected("BUNDLE_RESPONSE_MISMATCH")
    if projection != project(parts["coverage"], parts["source"], parts["recipe"]["fields"], parts["recipe"]["scope"]):
        raise Rejected("BUNDLE_PROJECTION_MISMATCH")
    if parts["assessment"] != assess_coverage(parts["coverage"], parts["source"], parts["gold"]):
        raise Rejected("BUNDLE_GOLD_ASSESSMENT_MISMATCH")
    if projection["coverageDigest"] != digest(parts["coverage"]) or projection["publicationAllowed"] is not False:
        raise Rejected("BUNDLE_COVERAGE_MISMATCH")
    if parts["assessment"]["coverageDigest"] != digest(parts["coverage"]):
        raise Rejected("BUNDLE_ASSESSMENT_MISMATCH")
    ir = projection["ir"]
    expected = [compile_rule(ir, r["id"]) for r in ir["rules"]] if ir else []
    if parts["compiled"] != expected:
        raise Rejected("BUNDLE_COMPILED_MISMATCH")
    binding = bind_rule_evidence(raw, parts["source"], parts["bridge"], ir) if ir else None
    if parts["binding"] != binding:
        raise Rejected("BUNDLE_BINDING_MISMATCH")
    return True
