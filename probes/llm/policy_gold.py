"""Frozen, hand-authored bounded policy gold. Never sent to the extraction model.

These are individual condition probes, NOT a complete interpretation of the law.
"""
SCOPE = {"regions": ["CN"], "institutions": ["poc-bank"],
         "products": ["ordinary-personal-loan"], "purposes": ["component-probe"],
         "validFrom": "2024-07-01", "validTo": None, "timezone": "Asia/Shanghai"}
HOST = {"region": "CN", "institution": "poc-bank", "product": "ordinary-personal-loan",
        "purpose": "component-probe", "business_date": "2024-07-02", "timezone": "Asia/Shanghai"}


def field(name, kind, values=None):
    return {"path": name, "type": kind, "sourceKind": "INPUT", "required": False,
            "values": values or [], "minimum": 1 if kind == "integer" else None,
            "maximum": 1200 if kind == "integer" else None}


FIELDS = [field("original_months", "integer"), field("extension_months", "integer"),
          field("months", "integer"), field("purpose_kind", "enum", ["CONSUMPTION", "BUSINESS"]),
          field("payment_mode", "enum", ["TRUSTEE", "SELF"])]
CASES = [
    {"id": "P43", "clauses": ["第四十三条"],
     "task": "仅提取第四十三条第二段中期限一年以内的展期累计上限这一项可计算子条件。一年以内含一年，单位为完整月。超过一年的分支需要除法，当前IR不支持，本任务不编译该分支。首段审慎评估和同意展期等业务前提未核验，单项结果不能代表展期许可。",
     "expectedRuleCount": 1, "category": "NUMERIC_SUBCONDITION_ONLY",
     "gold": [
         {"inputs": {"original_months": 12, "extension_months": 12}, "expected": "MET"},
         {"inputs": {"original_months": 12, "extension_months": 13}, "expected": "NOT_MET"},
         {"inputs": {"original_months": 6, "extension_months": 6}, "expected": "MET"},
         {"inputs": {"original_months": 6, "extension_months": 7}, "expected": "NOT_MET"},
         {"inputs": {"original_months": 13, "extension_months": 1}, "expected": "NOT_APPLICABLE"},
         {"inputs": {"original_months": 6}, "expected": "UNKNOWN"},
         {"inputs": {"original_months": True, "extension_months": 1}, "expected": "INVALID_INPUT"},
         {"inputs": {"original_months": 6, "extension_months": 1}, "host": {"business_date": "2024-06-30"}, "expected": "NOT_APPLICABLE"},
         {"inputs": {"original_months": 6, "extension_months": 1}, "host": {"business_date": "2024-02-30"}, "expected": "INVALID_INPUT"},
         {"inputs": {"original_months": 6, "extension_months": 1}, "host": {"product": "credit-card"}, "expected": "NOT_APPLICABLE"},
     ]},
    {"id": "P08", "clauses": ["第八条"],
     "task": "提取第八条的个人消费和生产经营期限两个分支；使用months及purpose_kind，年换算为完整月。保留一般、可适当延长、经营现金流回收周期及国家相关规定等未能独立确认的依据，不臆造资格字段或把最长十年当作一般五年。",
     "expectedRuleCount": 2, "category": "UNRESOLVED_EXTERNAL_AND_EXCEPTION",
     "requiredUnresolved": ["国家相关规定", "经营现金流回收周期"],
     "gold": [
         {"inputs": {"purpose_kind": "CONSUMPTION", "months": 60}, "expected": "REVIEW_REQUIRED"},
         {"inputs": {"purpose_kind": "CONSUMPTION", "months": 61}, "expected": "REVIEW_REQUIRED"},
         {"inputs": {"purpose_kind": "BUSINESS", "months": 60}, "expected": "REVIEW_REQUIRED"},
         {"inputs": {"purpose_kind": "BUSINESS", "months": 120}, "expected": "REVIEW_REQUIRED"},
     ]},
    {"id": "P33", "clauses": ["第三十三条"],
     "task": "提取第三十三条受托支付要求。这里只提供第三十三条，第三十六条尚未绑定到本次材料集合。保留未解析的引用，不凭记忆补充例外。使用payment_mode字段，不能审批支付。",
     "expectedRuleCount": 1, "category": "UNRESOLVED_CROSS_REFERENCE",
     "requiredUnresolved": ["第三十六条"],
     "gold": [
         {"inputs": {"payment_mode": "TRUSTEE"}, "expected": "REVIEW_REQUIRED"},
         {"inputs": {"payment_mode": "SELF"}, "expected": "REVIEW_REQUIRED"},
     ]},
]
