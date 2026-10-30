"""Fail-closed M1 templates, not a general natural-language rule compiler.

Templates recognize complete bounded source statements. No model AST is accepted.
The output is a numeric subcondition, never an approval or a whole-clause decision.
"""
import copy
import re

from knowledge_core.contracts import Rejected, digest
from probes.llm.coverage import canonical
from probes.llm.coverage_recipe import FIELDS, SCOPE
from probes.llm.linked import convert
from probes.llm.semantic_v2 import validate


VERSION = "verified-lowering.v0.1"
# This registry is a trusted engineering input, not supplied by the model.
REGISTRY = {
    "展期期限累计": {"field": "extension_months", "unit": "complete_month"},
    "原贷款期限": {"field": "original_months", "unit": "complete_month"},
    "贷款期限": {"field": "months", "unit": "complete_month"},
}
NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
NUMBER = r"(?:[1-9][0-9]?|[一二三四五六七八九十])"
PATTERNS = {
    "bounded-field-comparison": rf"期限(?P<n>{NUMBER})年以内的贷款(?P<left>展期期限累计)不得超过(?P<right>原贷款期限)",
    "purpose-duration-bound": rf"用于(?P<purpose>个人消费|生产经营)的(?P<left>贷款期限)(?P<general>一般)?(?:不得超过|不超过)(?P<n>{NUMBER})年",
}
CONFIG = {"version": VERSION, "registry": REGISTRY, "numbers": NUMBERS,
          "patterns": PATTERNS, "fields": FIELDS, "scope": SCOPE,
          "conversion": {"yearToCompleteMonths": 12, "partialMonths": "REJECT_UPSTREAM"}}


def comparison(op, left, right, field=False, kind="integer"):
    return {"op": op, "left": {"field": left},
            "right": {"field": right} if field else {"literal": {"type": kind, "value": right}}}


def recognize(quote, source):
    """Only exact statements at source boundaries qualify; matching a substring is unsafe."""
    if source["content"].count(quote) != 1:
        return {"status": "UNVERIFIABLE", "reason": "ANCHOR_NOT_UNIQUE"}
    start = source["content"].index(quote)
    end = start + len(quote)
    before, after = source["content"][:start], source["content"][end:]
    if before and before[-1] not in " \n。；，" or after and after[0] not in " \n。；，":
        return {"status": "UNVERIFIABLE", "reason": "PARTIAL_STATEMENT"}
    if "一半" in quote:
        return {"status": "UNSUPPORTED", "reason": "ARITHMETIC_NOT_IN_IR"}
    for name, pattern in PATTERNS.items():
        hit = re.fullmatch(pattern, quote)
        if not hit:
            continue
        terms = hit.groupdict()
        years = NUMBERS[terms["n"]] if terms["n"] in NUMBERS else int(terms["n"])
        lhs = REGISTRY[terms["left"]]["field"]
        unresolved = []
        if name == "bounded-field-comparison":
            rhs = REGISTRY[terms["right"]]["field"]
            predicate = comparison("lte", lhs, rhs, field=True)
            applies = comparison("lte", rhs, years * 12)
        else:
            predicate = comparison("lte", lhs, years * 12)
            applies = comparison("eq", "purpose_kind",
                                 "CONSUMPTION" if terms["purpose"] == "个人消费" else "BUSINESS", kind="enum")
            if terms["general"]:
                unresolved.append(quote)
        # External prerequisites cannot be removed by omitting a model relation.
        external = "个人贷款的期限应符合国家相关规定"
        if external in source["content"]:
            unresolved.append(external)
        return {"status": "VERIFIED_NUMERIC", "template": name,
                "predicate": predicate, "appliesWhen": applies, "unresolvedQuotes": unresolved,
                "operands": terms, "unit": "complete_month"}
    return {"status": "UNVERIFIABLE", "reason": "NO_COMPLETE_SUPPORTED_TEMPLATE"}


def lower(output, source):
    units = validate(output, source)
    decisions, rules = [], []
    for u in units.values():
        decision = recognize(u["quote"], source)
        if decision["status"] == "VERIFIED_NUMERIC" and decision["template"] == "purpose-duration-bound":
            subject = "用于" + decision["operands"]["purpose"]
            if u["branchQuote"] is None or subject not in u["branchQuote"]:
                decision = {"status": "UNVERIFIABLE", "reason": "BRANCH_BINDING_NOT_CONFIRMED"}
        if decision["status"] == "VERIFIED_NUMERIC" and (u["kind"] != "CONDITION" or u["state"] != "PROPOSED_NUMERIC"):
            decision = {"status": "MANUAL", "reason": "NOT_PROPOSED_AS_NUMERIC_CONDITION"}
        if decision["status"] == "VERIFIED_NUMERIC":
            # Preserve every direct/transitive dependency as unresolved, not assumed satisfied.
            pending, dependencies = [u["id"]], set()
            while pending:
                node = pending.pop()
                for r in output["relations"]:
                    if r["from"] == node and r["type"] == "requires" and r["to"] not in dependencies:
                        dependencies.add(r["to"])
                        pending.append(r["to"])
            if u["id"] in dependencies:
                raise Rejected("CYCLIC_CONDITION_DEPENDENCY")
            unresolved = sorted(set(decision["unresolvedQuotes"] + [units[i]["quote"] for i in dependencies]))
            rules.append({"id": u["id"], "title": "Numeric subcondition only: " + u["id"],
                "predicate": decision["predicate"], "appliesWhen": decision["appliesWhen"],
                "scope": copy.deepcopy(SCOPE), "quotes": [u["quote"]], "exceptions": [],
                "unresolvedQuotes": unresolved})
        decisions.append({"unitId": u["id"], "quote": u["quote"], **decision})
    ir = convert({"rules": rules}, source, FIELDS, SCOPE) if rules else None
    return {"version": VERSION, "sourceDigest": digest(source), "semanticDigest": digest(output),
            "configDigest": digest(CONFIG), "decisions": decisions, "ir": ir,
            "resultScope": "NUMERIC_SUBCONDITION_ONLY", "wholeClauseDecision": "REVIEW_REQUIRED",
            "businessOwnerApproved": False, "publicationAllowed": False}


def inspect_legacy(unit, source):
    """Retrospective rejection check, never silently repair or execute a legacy AST."""
    proof = recognize(unit["quote"], source)
    if unit["predicate"] is None:
        return {"status": "NO_FORMULA", "publicationAllowed": False}
    matched = proof["status"] == "VERIFIED_NUMERIC" and all(
        canonical(unit[k]) == canonical(proof[k]) for k in ("predicate", "appliesWhen"))
    return {"status": "TEMPLATE_MATCH_ONLY" if matched else "REJECTED_FORMULA",
            "proof": proof, "publicationAllowed": False}
