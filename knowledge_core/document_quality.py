"""Internal document-quality contracts.

These objects describe production and evaluation evidence. They are deliberately
separate from the published document v0.1 contracts: retrieval output, manifests,
authorization, and history replay remain byte-compatible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .contracts import Rejected, canonical, digest


UNIT_KINDS = ("CHAPTER", "SECTION", "ARTICLE", "PARAGRAPH", "ITEM", "ATTACHMENT")
CASE_KINDS = ("CANONICAL", "PARAPHRASE", "CONFUSABLE", "NO_ANSWER")
FAILURE_KINDS = (
    "RETRIEVAL_MISS",
    "RANKING_ERROR",
    "INSUFFICIENT_EVIDENCE",
    "FALSE_POSITIVE_NO_ANSWER",
    "ANCHOR_INVALID",
    "ANSWER_FACT_ERROR",
    "ANSWER_CITATION_ERROR",
)

ANCHOR = {
    "type": "object",
    "properties": {
        "xpath": {"type": "string", "minLength": 1, "maxLength": 2000},
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
        "quote": {"type": "string", "minLength": 1, "maxLength": 200000},
    },
    "required": ["xpath", "start", "end", "quote"],
    "additionalProperties": False,
}

DOCUMENT_UNIT = {
    "type": "object",
    "properties": {
        "unitId": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "kind": {"enum": list(UNIT_KINDS)},
        "label": {"type": ["string", "null"], "maxLength": 120},
        "title": {"type": ["string", "null"], "maxLength": 500},
        "titlePath": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 12,
        },
        "parentId": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
        "order": {"type": "integer", "minimum": 0},
        "text": {"type": "string", "minLength": 1, "maxLength": 500000},
        "textDigest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "sourceDigest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "anchors": {"type": "array", "items": ANCHOR, "minItems": 1, "maxItems": 1000},
    },
    "required": ["unitId", "kind", "label", "title", "titlePath", "parentId", "order",
                 "text", "textDigest", "sourceDigest", "anchors"],
    "additionalProperties": False,
}

RETRIEVAL_CHUNK = {
    "type": "object",
    "properties": {
        "chunkId": {"type": "string", "minLength": 1, "maxLength": 256},
        "text": {"type": "string", "minLength": 1, "maxLength": 500000},
        "textDigest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "unitIds": {
            "type": "array", "items": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "minItems": 1, "uniqueItems": True,
        },
        "titlePaths": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    },
    "required": ["chunkId", "text", "textDigest", "unitIds", "titlePaths"],
    "additionalProperties": False,
}

RETRIEVAL_CANDIDATE = {
    "type": "object",
    "properties": {
        "rank": {"type": "integer", "minimum": 1},
        "chunkId": {"type": "string", "minLength": 1, "maxLength": 256},
        "unitIds": {
            "type": "array", "items": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "minItems": 1, "uniqueItems": True,
        },
        "scoreBps": {"type": ["integer", "null"], "minimum": 0, "maximum": 10000},
        "termScoreBps": {"type": ["integer", "null"], "minimum": 0, "maximum": 10000},
        "vectorScoreBps": {"type": ["integer", "null"], "minimum": 0, "maximum": 10000},
        "selected": {"type": "boolean"},
    },
    "required": ["rank", "chunkId", "unitIds", "scoreBps", "termScoreBps",
                 "vectorScoreBps", "selected"],
    "additionalProperties": False,
}

QUALITY_CASE = {
    "type": "object",
    "properties": {
        "caseId": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,79}$"},
        "category": {"enum": list(CASE_KINDS)},
        "question": {"type": "string", "minLength": 2, "maxLength": 500},
        "expectedClauses": {
            "type": "array", "items": {"type": "string", "minLength": 2, "maxLength": 120},
            "maxItems": 6, "uniqueItems": True,
        },
        "answerFacts": {
            "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 12, "uniqueItems": True,
        },
        "forbiddenClaims": {
            "type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 12, "uniqueItems": True,
        },
    },
    "required": ["caseId", "category", "question", "expectedClauses", "answerFacts",
                 "forbiddenClaims"],
    "additionalProperties": False,
}

QUALITY_TEST_SET = {
    "type": "object",
    "properties": {
        "schemaVersion": {"const": "document-quality-test-set.v0.1"},
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,79}$"},
        "purpose": {"enum": ["TUNING", "FROZEN_ACCEPTANCE"]},
        "sourceDigest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "sourceTitle": {"type": "string", "minLength": 1, "maxLength": 200},
        "cases": {"type": "array", "items": QUALITY_CASE, "minItems": 1, "maxItems": 100},
    },
    "required": ["schemaVersion", "id", "purpose", "sourceDigest", "sourceTitle", "cases"],
    "additionalProperties": False,
}

QUALITY_EVALUATION = {
    "type": "object",
    "properties": {
        "schemaVersion": {"const": "document-quality-evaluation.v0.1"},
        "testSetDigest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "profile": {"type": "object"},
        "engineIdentity": {"type": "string", "minLength": 1},
        "embeddingIdentity": {"type": "string", "minLength": 1},
        "metricsBps": {
            "type": "object",
            "properties": {
                "recallAt3": {"type": "integer", "minimum": 0, "maximum": 10000},
                "hitAt1": {"type": "integer", "minimum": 0, "maximum": 10000},
                "mrr": {"type": "integer", "minimum": 0, "maximum": 10000},
                "noAnswerFalsePositive": {"type": "integer", "minimum": 0, "maximum": 10000},
            },
            "required": ["recallAt3", "hitAt1", "mrr", "noAnswerFalsePositive"],
            "additionalProperties": False,
        },
        "latencyMs": {
            "type": "object",
            "properties": {"total": {"type": "integer", "minimum": 0},
                           "average": {"type": "integer", "minimum": 0}},
            "required": ["total", "average"], "additionalProperties": False,
        },
        "cases": {"type": "array", "items": {"type": "object"}, "minItems": 1},
    },
    "required": ["schemaVersion", "testSetDigest", "profile", "engineIdentity",
                 "embeddingIdentity", "metricsBps", "latencyMs", "cases"],
    "additionalProperties": False,
}


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_object(schema: dict, value: object, error: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        path = "/".join(map(str, errors[0].path)) or "$"
        raise Rejected(error, path)


def validate_test_set(value: object, available_clauses: set[str] | None = None) -> str:
    validate_object(QUALITY_TEST_SET, value, "QUALITY_TEST_SET_INVALID")
    cases = value["cases"]
    ids = [case["caseId"] for case in cases]
    questions = ["".join(case["question"].split()).casefold() for case in cases]
    if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
        raise Rejected("QUALITY_TEST_SET_DUPLICATE")
    for case in cases:
        no_answer = case["category"] == "NO_ANSWER"
        if no_answer != (case["expectedClauses"] == []):
            raise Rejected("QUALITY_NO_ANSWER_GOLD_INVALID", case["caseId"])
        if not no_answer and not case["answerFacts"]:
            raise Rejected("QUALITY_FACT_GOLD_REQUIRED", case["caseId"])
        if available_clauses is not None and set(case["expectedClauses"]) - available_clauses:
            raise Rejected("QUALITY_GOLD_CLAUSE_MISSING", case["caseId"])
    if value["purpose"] == "FROZEN_ACCEPTANCE":
        counts = {kind: sum(case["category"] == kind for case in cases) for kind in CASE_KINDS}
        if len(cases) != 30 or counts != {
                "CANONICAL": 6, "PARAPHRASE": 12, "CONFUSABLE": 6, "NO_ANSWER": 6}:
            raise Rejected("QUALITY_FROZEN_DISTRIBUTION_INVALID", json.dumps(counts, sort_keys=True))
    return digest(value)


def load_test_set(path: str | Path, available_clauses: set[str] | None = None) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Rejected("QUALITY_TEST_SET_JSON_INVALID") from None
    validate_test_set(value, available_clauses)
    return value


def evaluate_retrieval(test_set: dict, rows: list[dict], profile: dict,
                       engine_identity: str, embedding_identity: str) -> dict:
    """Score recorded candidate ranks; answer quality is evaluated separately."""
    validate_test_set(test_set)
    by_id = {row["caseId"]: row for row in rows}
    if set(by_id) != {case["caseId"] for case in test_set["cases"]}:
        raise Rejected("QUALITY_EVALUATION_CASE_MISMATCH")
    scored = []
    positives = no_answers = recall = hit = reciprocal_sum = false_positive = latency = 0
    for case in test_set["cases"]:
        row = by_id[case["caseId"]]
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise Rejected("QUALITY_EVALUATION_CANDIDATES_INVALID", case["caseId"])
        clauses = []
        for candidate in candidates:
            for clause in candidate.get("clauses", []):
                if clause not in clauses:
                    clauses.append(clause)
        selected = clauses[:3]
        expected = case["expectedClauses"]
        case_latency = row.get("latencyMs")
        if type(case_latency) is not int or case_latency < 0:
            raise Rejected("QUALITY_EVALUATION_LATENCY_INVALID", case["caseId"])
        latency += case_latency
        failures = []
        if expected:
            positives += 1
            complete = set(expected).issubset(selected)
            recall += complete
            hit += bool(selected and selected[0] in expected)
            ranks = [clauses.index(value) + 1 for value in expected if value in clauses]
            reciprocal_sum += 1 / min(ranks) if ranks else 0
            if not complete:
                failures.append("INSUFFICIENT_EVIDENCE" if set(expected) & set(selected) else "RETRIEVAL_MISS")
            elif not selected or selected[0] not in expected:
                failures.append("RANKING_ERROR")
        else:
            no_answers += 1
            if selected:
                false_positive += 1
                failures.append("FALSE_POSITIVE_NO_ANSWER")
        scored.append({**case, "candidates": candidates, "selectedClauses": selected,
                       "latencyMs": case_latency, "passed": not failures,
                       "failureClassifications": failures})
    evaluation = {
        "schemaVersion": "document-quality-evaluation.v0.1",
        "testSetDigest": digest(test_set), "profile": profile,
        "engineIdentity": engine_identity, "embeddingIdentity": embedding_identity,
        "metricsBps": {
            "recallAt3": 10000 * recall // positives if positives else 0,
            "hitAt1": 10000 * hit // positives if positives else 0,
            "mrr": int(10000 * reciprocal_sum / positives) if positives else 0,
            "noAnswerFalsePositive": 10000 * false_positive // no_answers if no_answers else 0,
        },
        "latencyMs": {"total": latency, "average": latency // len(scored)}, "cases": scored,
    }
    validate_object(QUALITY_EVALUATION, evaluation, "QUALITY_EVALUATION_INVALID")
    return evaluation
