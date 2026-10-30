"""Synthetic fixtures only; no actual bank policy or extracted truth."""

import copy
import json
from pathlib import Path

from knowledge_core.contracts import digest, text_digest
from knowledge_core.core import Actor, BusinessContext, Core


PRIVILEGES = frozenset({"policy.manage", "source.register", "source.activate", "gold.manage",
    "recipe.edit", "artifact.produce", "candidate.validate", "rule.approve", "manifest.publish", "binding.manage"})
AUTHOR = Actor("tenant-a", "author", "synthetic-authority-v1", PRIVILEGES)
READER = Actor("tenant-a", "reader", "synthetic-login-v1")
CONTEXT = BusinessContext("2026-11-15", "CN-BJ", "demo-bank", "business-loan", "condition-check", "fixed-test-clock")
CASES = json.loads((Path(__file__).parent / "fixtures/rule-cases.json").read_text())


def source(product="credit", revision=1):
    content = ("Synthetic demonstration, not bank-approved policy.\n\n"
        "Business age must be at least three years; special industries require review.\n"
        "Requested term must not exceed 36 months.\n"
        "A valid license is required.") if product == "credit" else "Service hours are 09:00 to 17:00.\nSynthetic FAQ; verify before real use."
    return {"schemaVersion": "source-revision.v0.1", "id": product + "-source", "revision": revision,
            "mediaType": "text/plain", "content": content, "contentDigest": text_digest(content)}


def refs(src):
    lines = (3, 4, 5) if src["id"] == "credit-source" else (1, 2)
    return [{"sourceDigest": digest(src), "lineStart": line, "lineEnd": line,
             "quoteDigest": text_digest(src["content"].splitlines()[line - 1])} for line in lines]


def ir(src=None):
    src = src or source()
    evidence = refs(src)
    def field(path, kind, host=False, values=None, low=None, high=None):
        return {"path": path, "type": kind, "sourceKind": "HOST" if host else "INPUT", "required": False,
                "values": values or [], "minimum": low, "maximum": high}
    scope = {"regions": ["CN-BJ"], "institutions": ["demo-bank"], "products": ["business-loan"],
             "purposes": ["condition-check"], "validFrom": "2026-01-01", "validTo": None, "timezone": "Asia/Shanghai"}
    def rule(name, predicate, ref):
        return {"id": name, "title": name + " synthetic condition", "evidenceRefs": [ref],
                "scope": copy.deepcopy(scope), "predicate": predicate, "exceptions": [], "unresolved": [], "onMissing": "UNKNOWN"}
    age = rule("age", {"op": "years_at_least", "start": {"field": "registration_date"}, "asOf": {"field": "business_date"},
                        "years": 3, "anniversary": "FEB29_TO_FEB28"}, evidence[0])
    age["exceptions"] = [{"id": "special-industry", "when": {"op": "eq", "left": {"field": "industry"},
                          "right": {"literal": {"type": "enum", "value": "special"}}},
                          "outcome": "REVIEW_REQUIRED", "evidenceRefs": [evidence[0]]}]
    return {"schemaVersion": "rule-ir.v0.1", "id": "credit-conditions", "revision": 1, "classification": "DEMO",
            "fields": [field("registration_date", "date"), field("business_date", "date", host=True),
                       field("industry", "enum", values=["ordinary", "special"]),
                       field("months", "integer", low=1, high=120), field("license_valid", "boolean")],
            "rules": [age, rule("months", {"op": "lte", "left": {"field": "months"},
                "right": {"literal": {"type": "integer", "value": 36}}}, evidence[1]),
                rule("license", {"op": "eq", "left": {"field": "license_valid"},
                "right": {"literal": {"type": "boolean", "value": True}}}, evidence[2])]}


def policy(revision=1, source_reader=True, history=True):
    grants = []
    for principal in ("author", "reader"):
        for product in ("credit", "faq"):
            grants.append({"principal": principal, "resource": "product:" + product,
                           "actions": ["consume", "history"] if history else ["consume"]})
            if principal == "author" or source_reader:
                grants.append({"principal": principal, "resource": "source:" + product + "-source", "actions": ["source_read"]})
    return {"schemaVersion": "active-policy.v0.1", "revision": revision, "grants": grants}


def prepare(core, product="credit", rule_set=None):
    src = source(product)
    src_sha = core.register_source(AUTHOR, src)
    core.activate_source(AUTHOR, src_sha, "2026-01-01")
    evidence = refs(src)
    tests = {"schemaVersion": "test-set.v0.1", "id": product + "-gold", "revision": 1,
             "ruleCases": [{**case, "host": {**CONTEXT.facts(), **case.get("host", {})}} for case in CASES] if product == "credit" else [],
             "evidenceCases": evidence}
    tests_sha = core.register_test_set(AUTHOR, tests)
    recipe = {"schemaVersion": "recipe.v0.1", "id": product + "-recipe", "revision": 1, "productId": product,
              "sourceDigests": [src_sha], "processes": ["document", "rule"] if product == "credit" else ["document"],
              "testSetDigest": tests_sha, "intendedConsumers": ["reader"], "intendedHistoryReaders": ["reader"], "versionPolicy": "PINNED"}
    recipe_sha = core.save_recipe(AUTHOR, recipe, 0)
    rules_sha = core.register_rule_set(AUTHOR, rule_set or ir(src)) if product == "credit" else None
    artifact = {"schemaVersion": "artifact.v0.1", "id": product + "-artifact", "revision": 1,
                "kind": "rules" if product == "credit" else "evidence", "sourceDigests": [src_sha],
                "scope": ir()["rules"][0]["scope"],
                "evidence": evidence, "ruleSetDigest": rules_sha}
    artifact_sha = core.register_artifact(AUTHOR, artifact)
    candidate = core.create_candidate(AUTHOR, recipe_sha, [artifact_sha])
    validation = core.validate_candidate(AUTHOR, candidate)
    coverage = [{"sourceDigest": src_sha, "lineStart": 1, "lineEnd": 2, "disposition": "NON_NORMATIVE", "reason": "Synthetic header and blank line", "ruleIds": []}]
    coverage += [{"sourceDigest": src_sha, "lineStart": line, "lineEnd": line, "disposition": "MODELED", "reason": "Manually reviewed synthetic rule and exception", "ruleIds": [name]} for line, name in [(3, "age"), (4, "months"), (5, "license")]]
    return {"source": src, "sourceDigest": src_sha, "tests": tests, "recipe": recipe,
            "recipeDigest": recipe_sha, "artifact": artifact, "artifactDigest": artifact_sha,
            "candidate": candidate, "validation": validation, "coverage": coverage}


def publish(core, product="credit"):
    data = prepare(core, product)
    approval = core.approve(AUTHOR, data["candidate"], data["validation"], data["coverage"]) if product == "credit" else None
    manifest = core.publish(AUTHOR, data["candidate"], data["validation"], approval, 1)
    binding = core.bind(AUTHOR, manifest, 0)
    return {**data, "approval": approval, "manifest": manifest, "binding": binding}


def consume(core, product="credit"):
    return core.consume(READER, product, CONTEXT, {"registration_date": "2020-01-01", "industry": "ordinary"} if product == "credit" else {}, "age" if product == "credit" else None)
