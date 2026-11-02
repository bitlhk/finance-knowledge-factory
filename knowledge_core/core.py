"""Persistent M0 state boundary. No network server, IAM replacement or scheduler."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .contracts import Rejected, canonical, digest, strict_date, text_digest, validate
from .rules import evaluate, in_scope, validate_ir, validate_scope


@dataclass(frozen=True)
class Actor:
    """Supplied by an authenticated host, never deserialized from client input."""
    tenant: str
    principal: str
    authority: str
    privileges: frozenset = field(default_factory=frozenset)

    def require(self, action):
        if action not in self.privileges or not self.authority:
            raise Rejected("FORBIDDEN", action)


@dataclass(frozen=True)
class BusinessContext:
    business_date: str
    region: str
    institution: str
    product: str
    purpose: str
    source: str
    timezone: str = "Asia/Shanghai"

    def facts(self):
        strict_date(self.business_date)
        if not all(isinstance(value, str) and value for value in (
            self.source, self.region, self.institution, self.product, self.purpose, self.timezone
        )):
            raise Rejected("TRUSTED_CONTEXT_REQUIRED")
        return {"business_date": self.business_date, "region": self.region,
                "institution": self.institution, "product": self.product,
                "purpose": self.purpose, "timezone": self.timezone}


class Core:
    def __init__(self, database):
        self.db = sqlite3.connect(database, isolation_level=None, timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS objects (
            tenant TEXT, digest TEXT, kind TEXT, body TEXT NOT NULL,
            PRIMARY KEY(tenant,digest));
          CREATE TABLE IF NOT EXISTS identities (
            tenant TEXT, kind TEXT, name TEXT, revision INTEGER, digest TEXT NOT NULL,
            PRIMARY KEY(tenant,kind,name,revision));
          CREATE TABLE IF NOT EXISTS heads (
            tenant TEXT, kind TEXT, name TEXT, revision INTEGER, digest TEXT NOT NULL,
            PRIMARY KEY(tenant,kind,name));
          CREATE TABLE IF NOT EXISTS activations (
            tenant TEXT, source TEXT, effective TEXT, digest TEXT,
            PRIMARY KEY(tenant,source,effective));
          CREATE TRIGGER IF NOT EXISTS immutable_object_update BEFORE UPDATE ON objects
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OBJECT'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_object_delete BEFORE DELETE ON objects
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_OBJECT'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_activation_update BEFORE UPDATE ON activations
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_ACTIVATION'); END;
          CREATE TRIGGER IF NOT EXISTS immutable_activation_delete BEFORE DELETE ON activations
            BEGIN SELECT RAISE(ABORT,'IMMUTABLE_ACTIVATION'); END;
        """)
        self.execution_count = 0

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _put(self, actor, kind, body):
        sha = validate(kind, body) if kind != "receipt" else digest(body)
        self.db.execute("INSERT OR IGNORE INTO objects VALUES(?,?,?,?)",
                        (actor.tenant, sha, kind, canonical(body)))
        if "id" in body and "revision" in body:
            key = (actor.tenant, kind, body["id"], body["revision"])
            existing = self.db.execute("SELECT digest FROM identities WHERE tenant=? AND kind=? AND name=? AND revision=?", key).fetchone()
            if existing and existing[0] != sha:
                raise Rejected("IMMUTABLE_REVISION")
            self.db.execute("INSERT OR IGNORE INTO identities VALUES(?,?,?,?,?)", (*key, sha))
        return sha

    def _get(self, actor, sha, kind):
        row = self.db.execute("SELECT body,kind FROM objects WHERE tenant=? AND digest=?", (actor.tenant, sha)).fetchone()
        if not row or row[1] != kind:
            raise Rejected("NOT_FOUND", kind)
        body = json.loads(row[0])
        if digest(body) != sha:
            raise Rejected("DIGEST_MISMATCH")
        return body

    def _head(self, actor, kind, name):
        row = self.db.execute("SELECT revision,digest FROM heads WHERE tenant=? AND kind=? AND name=?", (actor.tenant, kind, name)).fetchone()
        return row if row else (0, None)

    def _advance(self, actor, kind, name, sha, expected):
        revision, _ = self._head(actor, kind, name)
        if revision != expected:
            raise Rejected("VERSION_CONFLICT")
        self.db.execute("INSERT INTO heads VALUES(?,?,?,?,?) ON CONFLICT(tenant,kind,name) DO UPDATE SET revision=excluded.revision,digest=excluded.digest",
                        (actor.tenant, kind, name, revision + 1, sha))

    def _permit(self, actor, resource, action):
        _, sha = self._head(actor, "policy", "current")
        if sha:
            policy = self._get(actor, sha, "active-policy")
            if any(g["principal"] == actor.principal and g["resource"] == resource and action in g["actions"] for g in policy["grants"]):
                return
        raise Rejected("FORBIDDEN", action)

    def set_policy(self, actor, policy, expected_revision):
        actor.require("policy.manage")
        if policy["revision"] != expected_revision + 1:
            raise Rejected("VERSION_CONFLICT")
        with self.tx():
            sha = self._put(actor, "active-policy", policy)
            self._advance(actor, "policy", "current", sha, expected_revision)
        return sha

    def register_source(self, actor, source):
        actor.require("source.register")
        validate("source-revision", source)
        if text_digest(source["content"]) != source["contentDigest"]:
            raise Rejected("DIGEST_MISMATCH")
        with self.tx():
            return self._put(actor, "source-revision", source)

    def activate_source(self, actor, source_digest, effective_from, state="ACTIVE"):
        actor.require("source.activate")
        strict_date(effective_from)
        with self.tx():
            source = self._get(actor, source_digest, "source-revision")
            latest = self.db.execute("SELECT MAX(effective) FROM activations WHERE tenant=? AND source=?", (actor.tenant, source["id"])).fetchone()[0]
            if latest and effective_from <= latest:
                raise Rejected("ACTIVATION_ORDER_CONFLICT")
            event = {"schemaVersion": "source-activation.v0.1", "sourceId": source["id"],
                     "sourceDigest": source_digest, "effectiveFrom": effective_from,
                     "state": state, "authorityRef": actor.authority}
            sha = self._put(actor, "source-activation", event)
            self.db.execute("INSERT INTO activations VALUES(?,?,?,?)", (actor.tenant, source["id"], effective_from, sha))
        return sha

    def _source_access(self, actor, source_digest):
        source = self._get(actor, source_digest, "source-revision")
        self._permit(actor, "source:" + source["id"], "source_read")
        return source

    def _source_current(self, actor, source_digest, business_date):
        source = self._source_access(actor, source_digest)
        row = self.db.execute("SELECT digest FROM activations WHERE tenant=? AND source=? AND effective<=? ORDER BY effective DESC LIMIT 1",
                              (actor.tenant, source["id"], business_date)).fetchone()
        if not row:
            raise Rejected("SOURCE_NOT_EFFECTIVE")
        event = self._get(actor, row[0], "source-activation")
        if event["state"] != "ACTIVE" or event["sourceDigest"] != source_digest:
            raise Rejected("SOURCE_SUPERSEDED_OR_REVOKED")
        return row[0]

    def _evidence(self, actor, ref):
        source = self._source_access(actor, ref["sourceDigest"])
        lines = source["content"].splitlines()
        start, end = ref["lineStart"], ref["lineEnd"]
        if start < 1 or end < start or end > len(lines):
            raise Rejected("INVALID_LOCATOR")
        quote = "\n".join(lines[start - 1:end])
        if text_digest(quote) != ref["quoteDigest"]:
            raise Rejected("QUOTE_MISMATCH")
        return quote

    def register_test_set(self, actor, tests):
        actor.require("gold.manage")
        validate("test-set", tests)
        ids = [case["id"] for case in tests["ruleCases"]]
        if len(ids) != len(set(ids)) or not (ids or tests["evidenceCases"]):
            raise Rejected("INVALID_TEST_SET")
        with self.tx():
            return self._put(actor, "test-set", tests)

    def save_recipe(self, actor, recipe, expected_revision):
        actor.require("recipe.edit")
        validate("recipe", recipe)
        with self.tx():
            if recipe["revision"] != expected_revision + 1:
                raise Rejected("VERSION_CONFLICT")
            for sha in recipe["sourceDigests"]:
                self._source_access(actor, sha)
            self._get(actor, recipe["testSetDigest"], "test-set")
            sha = self._put(actor, "recipe", recipe)
            self._advance(actor, "recipe", recipe["id"], sha, expected_revision)
        return sha

    def register_rule_set(self, actor, ir):
        actor.require("artifact.produce")
        validate_ir(ir)
        if any(f["sourceKind"] == "HOST" and f["path"] != "business_date" for f in ir["fields"]):
            raise Rejected("HOST_FIELD_NOT_SUPPORTED")
        with self.tx():
            for rule in ir["rules"]:
                refs = rule["evidenceRefs"] + [u["evidenceRef"] for u in rule["unresolved"]]
                refs += [ref for e in rule["exceptions"] for ref in e["evidenceRefs"]]
                for ref in refs:
                    self._evidence(actor, ref)
            return self._put(actor, "rule-ir", ir)

    def register_artifact(self, actor, artifact):
        actor.require("artifact.produce")
        validate("artifact", artifact)
        validate_scope(artifact["scope"])
        with self.tx():
            for sha in artifact["sourceDigests"]:
                self._source_access(actor, sha)
            refs = list(artifact["evidence"])
            if artifact["kind"] == "rules":
                ir = self._get(actor, artifact["ruleSetDigest"], "rule-ir")
                for rule in ir["rules"]:
                    refs += rule["evidenceRefs"] + [u["evidenceRef"] for u in rule["unresolved"]]
                    refs += [ref for e in rule["exceptions"] for ref in e["evidenceRefs"]]
            elif artifact["ruleSetDigest"] is not None:
                raise Rejected("ARTIFACT_KIND_MISMATCH")
            for ref in refs:
                if ref["sourceDigest"] not in artifact["sourceDigests"]:
                    raise Rejected("UNDECLARED_SOURCE")
                self._evidence(actor, ref)
            return self._put(actor, "artifact", artifact)

    def create_candidate(self, actor, recipe_digest, artifact_digests):
        actor.require("artifact.produce")
        with self.tx():
            recipe = self._get(actor, recipe_digest, "recipe")
            artifacts = [self._get(actor, sha, "artifact") for sha in artifact_digests]
            has_rules = any(a["kind"] == "rules" for a in artifacts)
            if has_rules != ("rule" in recipe["processes"]):
                raise Rejected("PROCESS_ARTIFACT_MISMATCH")
            if {s for a in artifacts for s in a["sourceDigests"]} != set(recipe["sourceDigests"]):
                raise Rejected("SOURCE_CLOSURE_MISMATCH")
            candidate = {"schemaVersion": "candidate.v0.1", "productId": recipe["productId"],
                         "recipeDigest": recipe_digest, "artifactDigests": artifact_digests,
                         "testSetDigest": recipe["testSetDigest"]}
            return self._put(actor, "candidate", candidate)

    def _parts(self, actor, candidate_digest):
        candidate = self._get(actor, candidate_digest, "candidate")
        recipe = self._get(actor, candidate["recipeDigest"], "recipe")
        artifacts = [self._get(actor, sha, "artifact") for sha in candidate["artifactDigests"]]
        rules = [self._get(actor, a["ruleSetDigest"], "rule-ir") for a in artifacts if a["kind"] == "rules"]
        ids = [rule["id"] for ir in rules for rule in ir["rules"]]
        if len(ids) != len(set(ids)):
            raise Rejected("AMBIGUOUS_RULE_ID")
        return candidate, recipe, artifacts, rules

    def validate_candidate(self, actor, candidate_digest):
        actor.require("candidate.validate")
        with self.tx():
            candidate, _, artifacts, rule_sets = self._parts(actor, candidate_digest)
            tests = self._get(actor, candidate["testSetDigest"], "test-set")
            rule_map = {rule["id"]: ir for ir in rule_sets for rule in ir["rules"]}
            tested_ids = {case["ruleId"] for case in tests["ruleCases"]}
            results = []
            def record(name, expected, actual):
                results.append({"id": name, "expected": expected, "actual": actual, "passed": expected == actual})
            record("rule-coverage", canonical(sorted(rule_map)), canonical(sorted(tested_ids)))
            refs = {digest(ref) for a in artifacts for ref in a["evidence"]}
            record("evidence-coverage", canonical(sorted(refs)), canonical(sorted(digest(ref) for ref in tests["evidenceCases"])))
            for case in tests["ruleCases"]:
                actual = evaluate(rule_map[case["ruleId"]], case["ruleId"], case["inputs"], case["host"])["decision"] if case["ruleId"] in rule_map else "UNKNOWN_RULE"
                record(case["id"], case["expected"], actual)
            for index, ref in enumerate(tests["evidenceCases"]):
                try:
                    self._evidence(actor, ref)
                    actual = "MATCH"
                except Rejected as exc:
                    actual = exc.code
                record(f"evidence-{index}", "MATCH", actual)
            validation = {"schemaVersion": "validation.v0.1", "candidateDigest": candidate_digest,
                          "testSetDigest": candidate["testSetDigest"], "engine": "m0-reference-0.1.0",
                          "passed": all(row["passed"] for row in results), "results": results}
            return self._put(actor, "validation", validation)

    def approve(self, actor, candidate_digest, validation_digest, coverage_entries):
        actor.require("rule.approve")
        with self.tx():
            candidate, recipe, artifacts, rule_sets = self._parts(actor, candidate_digest)
            self._valid_result(actor, candidate_digest, validation_digest)
            if not rule_sets:
                raise Rejected("NO_RULE_APPROVAL_REQUIRED")
            rules = [r for ir in rule_sets for r in ir["rules"]]
            if any(rule["unresolved"] for rule in rules):
                raise Rejected("UNRESOLVED_EXCEPTION")
            coverage = {"schemaVersion": "coverage.v0.1", "candidateDigest": candidate_digest,
                        "entries": coverage_entries, "actor": actor.principal, "authorityRef": actor.authority}
            validate("coverage", coverage)
            covered = set()
            rule_map = {r["id"]: r for r in rules}
            for entry in coverage_entries:
                source_sha = entry["sourceDigest"]
                if source_sha not in recipe["sourceDigests"]:
                    raise Rejected("UNDECLARED_SOURCE")
                lines = self._source_access(actor, source_sha)["content"].splitlines()
                start, end = entry["lineStart"], entry["lineEnd"]
                if not 1 <= start <= end <= len(lines):
                    raise Rejected("INVALID_LOCATOR")
                if entry["disposition"] == "UNRESOLVED":
                    raise Rejected("UNRESOLVED_EXCEPTION")
                if entry["disposition"] == "MODELED" and not entry["ruleIds"]:
                    raise Rejected("COVERAGE_RULE_REQUIRED")
                if entry["disposition"] == "NON_NORMATIVE" and entry["ruleIds"]:
                    raise Rejected("COVERAGE_CONTRADICTION")
                for rule_id in entry["ruleIds"]:
                    if rule_id not in rule_map or not any(ref["sourceDigest"] == source_sha and ref["lineStart"] <= end and ref["lineEnd"] >= start for ref in rule_map[rule_id]["evidenceRefs"]):
                        raise Rejected("COVERAGE_RULE_MISMATCH")
                for line in range(start, end + 1):
                    if (source_sha, line) in covered:
                        raise Rejected("COVERAGE_OVERLAP")
                    covered.add((source_sha, line))
            required = {(sha, index) for sha in recipe["sourceDigests"] for index, text in enumerate(self._source_access(actor, sha)["content"].splitlines(), 1) if text.strip()}
            if not required.issubset(covered):
                raise Rejected("COVERAGE_INCOMPLETE")
            coverage_sha = self._put(actor, "coverage", coverage)
            approval = {"schemaVersion": "approval.v0.1", "candidateDigest": candidate_digest,
                        "validationDigest": validation_digest,
                        "scopeDigest": digest({"artifacts": [a["scope"] for a in artifacts], "rules": [r["scope"] for r in rules]}),
                        "coverageDigest": coverage_sha, "actor": actor.principal, "authorityRef": actor.authority}
            return self._put(actor, "approval", approval)

    def _valid_result(self, actor, candidate_digest, validation_digest):
        candidate = self._get(actor, candidate_digest, "candidate")
        result = self._get(actor, validation_digest, "validation")
        if result["candidateDigest"] != candidate_digest or result["testSetDigest"] != candidate["testSetDigest"] or not result["passed"]:
            raise Rejected("VALIDATION_NOT_BOUND_OR_FAILED")

    def publish(self, actor, candidate_digest, validation_digest, approval_digest, revision):
        actor.require("manifest.publish")
        with self.tx():
            candidate, recipe, _, rules = self._parts(actor, candidate_digest)
            self._valid_result(actor, candidate_digest, validation_digest)
            if self._head(actor, "recipe", recipe["id"])[1] != candidate["recipeDigest"]:
                raise Rejected("DRAFT_CHANGED_REVALIDATE")
            if rules:
                approval = self._get(actor, approval_digest, "approval")
                if approval["candidateDigest"] != candidate_digest or approval["validationDigest"] != validation_digest:
                    raise Rejected("APPROVAL_NOT_BOUND")
            elif approval_digest is not None:
                raise Rejected("NO_RULE_APPROVAL_REQUIRED")
            manifest = {"schemaVersion": "manifest.v0.1", "id": recipe["productId"], "revision": revision,
                        "productId": recipe["productId"], "recipeDigest": candidate["recipeDigest"],
                        "candidateDigest": candidate_digest, "artifactDigests": candidate["artifactDigests"],
                        "sourceDigests": recipe["sourceDigests"], "validationDigest": validation_digest,
                        "approvalDigest": approval_digest, "mode": "M0_REFERENCE_ONLY"}
            return self._put(actor, "manifest", manifest)

    def bind(self, actor, manifest_digest, expected_revision):
        actor.require("binding.manage")
        with self.tx():
            manifest = self._get(actor, manifest_digest, "manifest")
            binding = {"schemaVersion": "runtime-binding.v0.1", "productId": manifest["productId"],
                       "revision": expected_revision + 1, "manifestDigest": manifest_digest, "versionPolicy": "PINNED"}
            sha = self._put(actor, "runtime-binding", binding)
            self._advance(actor, "binding", binding["productId"], sha, expected_revision)
        return sha

    def consume(self, actor, product_id, context, inputs=None, rule_id=None):
        # A single serialized transaction prevents policy/activation races during return construction.
        host = context.facts()
        with self.tx():
            self._permit(actor, "product:" + product_id, "consume")
            _, binding_sha = self._head(actor, "binding", product_id)
            binding = self._get(actor, binding_sha, "runtime-binding")
            manifest_sha = binding["manifestDigest"]
            manifest = self._get(actor, manifest_sha, "manifest")
            for sha in manifest["sourceDigests"]:
                self._source_current(actor, sha, context.business_date)
            _, _, artifacts, rule_sets = self._parts(actor, manifest["candidateDigest"])
            if any(not in_scope(artifact["scope"], host) for artifact in artifacts):
                raise Rejected("KNOWLEDGE_NOT_APPLICABLE")
            evidence = [{"reference": ref, "quote": self._evidence(actor, ref)} for a in artifacts for ref in a["evidence"]]
            if rule_id is not None:
                matching = [ir for ir in rule_sets if any(r["id"] == rule_id for r in ir["rules"])]
                if len(matching) != 1:
                    raise Rejected("UNKNOWN_RULE")
                result = evaluate(matching[0], rule_id, inputs if inputs is not None else {}, host)
            else:
                result = {"decision": "EVIDENCE_ONLY"}
            self.execution_count += 1
            receipt = {"schemaVersion": "receipt.v0.1", "mode": "M0_REFERENCE_ONLY", "productId": product_id,
                       "principal": actor.principal, "manifestDigest": manifest_sha, "bindingDigest": binding_sha,
                       "policyDigest": self._head(actor, "policy", "current")[1], "sourceDigests": manifest["sourceDigests"],
                       "inputs": inputs if inputs is not None else {}, "host": host, "contextSource": context.source,
                       "result": result, "evidence": evidence, "createdAt": datetime.now(timezone.utc).isoformat()}
            sha = self._put(actor, "receipt", receipt)
        return {"receiptDigest": sha, **receipt}

    def replay(self, actor, receipt_digest):
        with self.tx():
            receipt = self._get(actor, receipt_digest, "receipt")
            self._permit(actor, "product:" + receipt["productId"], "history")
            if receipt["principal"] != actor.principal:
                self._permit(actor, "receipt:" + receipt_digest, "history")
            for sha in receipt["sourceDigests"]:
                self._source_access(actor, sha)
            return {"receiptDigest": receipt_digest, "replay": True, "currentApplicability": "NOT_EVALUATED", **receipt}
