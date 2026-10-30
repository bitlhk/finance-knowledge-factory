"""Frozen engineer-authored semantic oracle. NEVER supplied to the model.

Not a legal opinion, business-owner approval or independent human blind test.
P09/P12 are held out from prompt tuning; all are public-source engineering cases.
"""
from probes.llm.policy_gold import CASES as OLD_CASES


def expr(op, left, right, kind="integer", field=False):
    return {"op": op, "left": {"field": left},
            "right": {"field": right} if field else {"literal": {"type": kind, "value": right}}}


def unit(key, quote, kind, state, predicate=None, applies=None):
    return {"key": key, "needles": [quote], "kind": kind, "state": state,
            "predicate": predicate, "appliesWhen": applies}


BUSINESS = expr("eq", "purpose_kind", "BUSINESS", "enum")
CONSUMPTION = expr("eq", "purpose_kind", "CONSUMPTION", "enum")
GOLD = {
    "P43": {"clause": "第四十三条", "split": "DEVELOPMENT", "units": [
        unit("assessment", "审慎评估展期原因和后续还款安排的可行性", "PRECONDITION", "MANUAL"),
        unit("consent", "同意展期的", "PRECONDITION", "MANUAL"),
        unit("reasonable_term", "根据还款来源等情况，合理确定展期期限", "PRECONDITION", "MANUAL"),
        unit("management", "加强对贷款的后续管理", "FOLLOW_UP", "MANUAL"),
        unit("classification", "按照实质风险状况进行风险分类", "FOLLOW_UP", "MANUAL"),
        unit("short", "期限一年以内的贷款展期期限累计不得超过原贷款期限", "CONDITION", "EXECUTABLE",
             expr("lte", "extension_months", "original_months", field=True), expr("lte", "original_months", 12)),
        unit("long", "期限超过一年的贷款展期期限累计不得超过原贷款期限的一半", "CONDITION", "UNSUPPORTED",
             applies=expr("gt", "original_months", 12)),
    ], "relations": [
        ["consent", "business_prerequisite", "assessment"],
        ["reasonable_term", "business_prerequisite", "consent"],
        ["short", "business_prerequisite", "reasonable_term"],
        ["long", "business_prerequisite", "reasonable_term"],
        ["short", "alternative_to", "long"],
        ["reasonable_term", "followed_by", "management"],
        ["reasonable_term", "followed_by", "classification"],
    ], "execution": {"short": OLD_CASES[0]["gold"]}},
    "P08": {"clause": "第八条", "split": "DEVELOPMENT", "units": [
        unit("national", "个人贷款的期限应符合国家相关规定", "REFERENCE", "EXTERNAL"),
        unit("consumption", "用于个人消费的贷款期限不得超过五年", "CONDITION", "EXECUTABLE",
             expr("lte", "months", 60), CONSUMPTION),
        unit("general", "一般不超过五年", "QUALIFIER", "MANUAL"),
        unit("business", "用于生产经营的贷款期限一般不超过五年", "CONDITION", "EXECUTABLE",
             expr("lte", "months", 60), BUSINESS),
        unit("cashflow", "贷款用途对应的经营现金流回收周期较长", "QUALIFIER", "MANUAL"),
        unit("extension", "可适当延长贷款期限", "QUALIFIER", "MANUAL"),
        unit("ceiling", "最长不超过十年", "CONDITION", "EXECUTABLE",
             expr("lte", "months", 120), BUSINESS),
    ], "relations": [
        ["consumption", "requires", "national"], ["business", "requires", "national"],
        ["business", "requires", "general"], ["extension", "requires", "cashflow"],
        ["ceiling", "requires", "extension"], ["ceiling", "requires", "national"],
        ["consumption", "alternative_to", "business"], ["business", "alternative_to", "ceiling"],
    ], "execution": {k: OLD_CASES[1]["gold"] for k in ("consumption", "business", "ceiling")}},
    "P09": {"clause": "第九条", "split": "HELD_OUT", "units": [
        unit("market", "个人贷款利率应当遵循利率市场化原则", "PRECONDITION", "MANUAL"),
        unit("national", "遵守国家有关规定", "REFERENCE", "EXTERNAL"),
        unit("agreement", "由借贷双方在遵守国家有关规定的前提下协商确定", "CONDITION", "MANUAL"),
    ], "relations": [["agreement", "requires", "national"], ["agreement", "business_prerequisite", "market"]],
        "execution": {}},
    "P12": {"clause": "第十二条", "split": "HELD_OUT", "units": [
        unit("identity", "具有完全民事行为能力的中华人民共和国公民或符合国家有关规定的境外自然人", "PRECONDITION", "MANUAL"),
        unit("purpose", "借款用途明确合法", "PRECONDITION", "MANUAL"),
        unit("terms", "贷款申请数额、期限和币种合理", "PRECONDITION", "MANUAL"),
        unit("repayment", "借款人具备还款意愿和还款能力", "PRECONDITION", "MANUAL"),
        unit("credit", "借款人信用状况良好", "PRECONDITION", "MANUAL"),
        unit("other", "贷款人要求的其他条件", "REFERENCE", "EXTERNAL"),
    ], "relations": [], "execution": {}},
}
