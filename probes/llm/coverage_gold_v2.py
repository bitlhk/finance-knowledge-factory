"""Post-observation engineering oracle, never model input or business approval."""
import copy

from probes.llm.coverage_gold import GOLD as V1


VERSION = "coverage-gold.v0.2"
PROVENANCE = {
    "reviewer": "CODEX_AI_ENGINEERING_REVIEW_AT_USER_REQUEST",
    "businessOwnerApproved": False, "postObservationRevision": True,
    "source": "evidence/m1-round3/sources/regulation.html",
    "review": "docs/M1-P43-P08-ENGINEERING-REVIEW.md",
    "changes": [
        {"id": "P43-trigger", "basis": "借款人申请贷款展期的", "reason": "Restore omitted trigger, not a numeric fact"},
        {"id": "P08-exception", "basis": "一般不超过五年", "reason": "Default and qualified extension are not freely selectable bounds"},
        {"id": "merged-units", "basis": "对于贷款用途对应的经营现金流回收周期较长的，可适当延长贷款期限",
         "reason": "Check atomic meanings and relation within a complete conditional span, not one-to-one unit counts"},
        {"id": "result-boundary", "basis": "同意展期的", "reason": "Numeric subcondition never establishes authorization or whole-clause compliance"},
    ],
}


def atom(key, needle, kind, branch=None):
    return {"key": key, "needle": needle, "kind": kind, "branch": branch}


GOLD = {}
for case in ("P43", "P08"):
    old = V1[case]
    GOLD[case] = {"clause": old["clause"], "split": "DEVELOPMENT_POST_OBSERVATION",
                  "atoms": [atom(u["key"], u["needles"][0], u["kind"]) for u in old["units"]],
                  "relations": copy.deepcopy(old["relations"]), "embeddedRelations": [],
                  "execution": copy.deepcopy(old["execution"])}
GOLD["P43"]["atoms"].insert(0, atom("trigger", "借款人申请贷款展期的", "PRECONDITION"))
GOLD["P43"]["relations"].append(["assessment", "business_prerequisite", "trigger"])
next(a for a in GOLD["P43"]["atoms"] if a["key"] == "long")["forbidNumeric"] = True
for a in GOLD["P08"]["atoms"]:
    if a["key"] == "consumption":
        a["branch"] = "用于个人消费"
    elif a["key"] != "national":
        a["branch"] = "用于生产经营"
GOLD["P08"]["relations"] = [
    ["consumption", "requires", "national"], ["business", "requires", "national"],
    ["extension", "requires", "cashflow"], ["ceiling", "requires", "extension"],
    ["ceiling", "requires", "national"], ["extension", "exception_to", "business"],
]
GOLD["P08"]["embeddedRelations"] = [
    {"edge": ["extension", "requires", "cashflow"],
     "quote": "对于贷款用途对应的经营现金流回收周期较长的，可适当延长贷款期限"},
    {"edge": ["ceiling", "requires", "extension"],
     "quote": "可适当延长贷款期限，最长不超过十年"},
]
GOLD["P13"] = {"clause": "第十三条", "split": "NEW_HELD_OUT_NO_PROMPT_TUNING",
    "atoms": [atom("application", "以书面形式提出个人贷款申请", "PRECONDITION"),
              atom("evidence", "提供能够证明其符合贷款条件的相关资料", "PRECONDITION")],
    "relations": [], "embeddedRelations": [], "execution": {}}
GOLD["P41"] = {"clause": "第四十一条", "split": "NEW_HELD_OUT_NO_PROMPT_TUNING",
    "atoms": [atom("tracking", "定期跟踪分析评估借款人履行借款合同约定内容的情况", "FOLLOW_UP"),
              atom("future", "作为与借款人后续合作的信用评价基础", "FOLLOW_UP")],
    "relations": [], "embeddedRelations": [], "execution": {}}
