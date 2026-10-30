"""Closed contracts. Exported JSON Schemas are generated from this registry."""

import hashlib
import json
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator


class Rejected(ValueError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(f"{code}: {detail}")


def canonical(value):
    # No float normalization ambiguity in content-addressed assets.
    def visit(item):
        if isinstance(item, float):
            raise Rejected("FLOAT_NOT_ALLOWED")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise Rejected("NON_STRING_KEY")
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strict_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise Rejected("INVALID_DATE", str(value))
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise Rejected("INVALID_DATE", value) from exc
    if parsed.isoformat() != value:
        raise Rejected("INVALID_DATE", value)
    return parsed


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


def arr(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum, "uniqueItems": True}


def enum(*values):
    return {"enum": list(values)}


STR = {"type": "string", "minLength": 1, "maxLength": 4096}
ID = {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
DATE = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
REV = {"type": "integer", "minimum": 1}
BOOL = {"type": "boolean"}
TYPES = enum("integer", "boolean", "date", "enum", "string")
DECISIONS = enum("MET", "NOT_MET", "UNKNOWN", "INVALID_INPUT", "NOT_APPLICABLE", "REVIEW_REQUIRED")
LITERAL = obj({"type": TYPES, "value": {"type": ["string", "integer", "boolean"]}})
OPERAND = {"oneOf": [obj({"field": ID}), obj({"literal": LITERAL})]}
EXPR = {"$ref": "#/$defs/expression"}
EXPRESSION = {"oneOf": [
    obj({"op": enum("eq", "ne", "lt", "lte", "gt", "gte"), "left": OPERAND, "right": OPERAND}),
    obj({"op": enum("all", "any"), "args": arr(EXPR, 1, 8)}),
    obj({"op": enum("not"), "arg": EXPR}),
    obj({"op": enum("in"), "value": OPERAND, "set": arr(LITERAL, 1, 50)}),
    obj({"op": enum("years_at_least"), "start": obj({"field": ID}), "asOf": obj({"field": ID}),
         "years": {"type": "integer", "minimum": 1, "maximum": 100},
         "anniversary": enum("FEB29_TO_FEB28")})]}
FIELD = obj({"path": ID, "type": TYPES, "sourceKind": enum("INPUT", "HOST"), "required": BOOL,
             "values": arr(STR, 0, 50), "minimum": {"type": ["integer", "null"]},
             "maximum": {"type": ["integer", "null"]}})
SCOPE = obj({"regions": arr(ID, 1), "institutions": arr(ID, 1), "products": arr(ID, 1),
             "purposes": arr(ID, 1), "validFrom": DATE, "validTo": {"anyOf": [DATE, {"type": "null"}]},
             "timezone": enum("Asia/Shanghai")})
EVIDENCE = obj({"sourceDigest": HASH, "lineStart": REV, "lineEnd": REV, "quoteDigest": HASH})
RULE = obj({"id": ID, "title": STR, "evidenceRefs": arr(EVIDENCE, 1), "scope": SCOPE,
            "predicate": EXPR, "exceptions": arr(obj({"id": ID, "when": EXPR,
                "outcome": enum("REVIEW_REQUIRED", "NOT_APPLICABLE"), "evidenceRefs": arr(EVIDENCE, 1)})),
            "unresolved": arr(obj({"reason": STR, "evidenceRef": EVIDENCE})), "onMissing": enum("UNKNOWN")})


def versioned(name, properties):
    return obj({"schemaVersion": {"const": f"{name}.v0.1"}, **properties})


SCHEMAS = {
    "rule-ir": versioned("rule-ir", {"id": ID, "revision": REV, "classification": enum("DEMO"),
        "fields": arr(FIELD, 1), "rules": arr(RULE, 1)}),
    "source-revision": versioned("source-revision", {"id": ID, "revision": REV,
        "mediaType": enum("text/plain"), "content": {"type": "string", "maxLength": 1000000}, "contentDigest": HASH}),
    "source-activation": versioned("source-activation", {"sourceId": ID, "sourceDigest": HASH,
        "effectiveFrom": DATE, "state": enum("ACTIVE", "REVOKED"), "authorityRef": STR}),
    "recipe": versioned("recipe", {"id": ID, "revision": REV, "productId": ID,
        "sourceDigests": arr(HASH, 1), "processes": arr(enum("document", "rule"), 1, 2),
        "testSetDigest": HASH, "intendedConsumers": arr(ID), "intendedHistoryReaders": arr(ID),
        "versionPolicy": enum("PINNED")}),
    "artifact": versioned("artifact", {"id": ID, "revision": REV,
        "kind": enum("evidence", "rules"), "sourceDigests": arr(HASH, 1),
        "evidence": arr(EVIDENCE, 1), "scope": SCOPE,
        "ruleSetDigest": {"anyOf": [HASH, {"type": "null"}]}}),
    "candidate": versioned("candidate", {"productId": ID, "recipeDigest": HASH,
        "artifactDigests": arr(HASH, 1), "testSetDigest": HASH}),
    "test-set": versioned("test-set", {"id": ID, "revision": REV,
        "ruleCases": arr(obj({"id": ID, "ruleId": ID, "inputs": {"type": "object"},
            "host": {"type": "object"}, "expected": DECISIONS})), "evidenceCases": arr(EVIDENCE)}),
    "validation": versioned("validation", {"candidateDigest": HASH, "testSetDigest": HASH,
        "engine": enum("m0-reference-0.1.0"), "passed": BOOL,
        "results": arr(obj({"id": STR, "expected": STR, "actual": STR, "passed": BOOL}), 1, 1000)}),
    "approval": versioned("approval", {"candidateDigest": HASH, "validationDigest": HASH,
        "scopeDigest": HASH, "coverageDigest": HASH, "actor": ID, "authorityRef": STR}),
    "coverage": versioned("coverage", {"candidateDigest": HASH,
        "entries": arr(obj({"sourceDigest": HASH, "lineStart": REV, "lineEnd": REV,
            "disposition": enum("MODELED", "NON_NORMATIVE", "UNRESOLVED"), "reason": STR,
            "ruleIds": arr(ID)}), 1, 1000), "actor": ID, "authorityRef": STR}),
    "manifest": versioned("manifest", {"id": ID, "revision": REV, "productId": ID,
        "recipeDigest": HASH, "candidateDigest": HASH, "artifactDigests": arr(HASH, 1),
        "sourceDigests": arr(HASH, 1), "validationDigest": HASH,
        "approvalDigest": {"anyOf": [HASH, {"type": "null"}]}, "mode": enum("M0_REFERENCE_ONLY")}),
    "active-policy": versioned("active-policy", {"revision": REV, "grants": arr(obj({
        "principal": ID, "resource": ID,
        "actions": arr(enum("consume", "history", "source_read"), 1)}), 0, 1000)}),
    "runtime-binding": versioned("runtime-binding", {"productId": ID, "revision": REV,
        "manifestDigest": HASH, "versionPolicy": enum("PINNED")}),
}
for name, schema in SCHEMAS.items():
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"urn:knowledge-core:{name}:v0.1"
SCHEMAS["rule-ir"]["$defs"] = {"expression": EXPRESSION}


def validate(kind, value):
    encoded = canonical(value)
    if len(encoded.encode("utf-8")) > 2_000_000:
        raise Rejected("CONTRACT_TOO_LARGE")
    if kind not in SCHEMAS:
        raise Rejected("UNKNOWN_CONTRACT", kind)
    errors = list(Draft202012Validator(SCHEMAS[kind]).iter_errors(value))
    if errors:
        error = errors[0]
        raise Rejected("SCHEMA_INVALID", f"{list(error.path)}: {error.message[:200]}")
    return digest(value)


def export_schemas(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in SCHEMAS.items():
        (directory / f"{name}-v0.1.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    export_schemas(Path(__file__).resolve().parents[1] / "contracts")
