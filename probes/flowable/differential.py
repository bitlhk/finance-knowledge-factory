"""Hand-authored gold for each supported AST operator; no generated expected scores."""
import copy

from knowledge_core.rules import evaluate
from probes.flowable.compiler import compile_rule, prepare
from tests.support import CONTEXT, ir


def additional_cases():
    models, cases = [], []
    def cmp(op, n=12):
        return {"op": op, "left": {"field": "months"}, "right": {"literal": {"type": "integer", "value": n}}}
    fixtures = [
        ("eq", cmp("eq"), 12, 11), ("ne", cmp("ne"), 11, 12),
        ("lt", cmp("lt"), 11, 12), ("lte", cmp("lte"), 12, 13),
        ("gt", cmp("gt"), 13, 12), ("gte", cmp("gte"), 12, 11),
        ("all", {"op":"all","args":[cmp("gte"),cmp("lte",24)]}, 18, 25),
        ("any", {"op":"any","args":[cmp("eq"),cmp("eq",24)]}, 24, 18),
        ("not", {"op":"not","arg":cmp("eq")}, 11, 12),
        ("in", {"op":"in","value":{"field":"months"},"set":[{"type":"integer","value":12},{"type":"integer","value":24}]},24,18),
    ]
    def add(name, predicate, inputs, expected, fields=None, exceptions=None):
        rule_set = ir()
        rule = copy.deepcopy(rule_set["rules"][1])
        rule.update(id=name, predicate=predicate, exceptions=exceptions or [])
        rule_set["rules"] = [rule]
        rule_set["fields"].extend(fields or [])
        compiled = compile_rule(rule_set, name)
        actual = evaluate(rule_set, name, inputs, CONTEXT.facts())["decision"]
        assert actual == expected, (name, actual, expected)
        models.append(compiled)
        cases.append({"id":name,"expected":expected,"reference":actual,"compiledDigest":compiled["compiledDigest"],
                      **prepare(rule_set,name,inputs,CONTEXT.facts(),compiled)})
    for name, predicate, yes, no in fixtures:
        add("AST-"+name+"-true",predicate,{"months":yes},"MET")
        add("AST-"+name+"-false",predicate,{"months":no},"NOT_MET")
    add("AST-date-eq", {"op":"eq","left":{"field":"registration_date"},"right":{"literal":{"type":"date","value":"2024-02-29"}}},
        {"registration_date":"2024-02-29"},"MET")
    add("AST-date-lt", {"op":"lt","left":{"field":"registration_date"},"right":{"field":"business_date"}},
        {"registration_date":"2026-11-16"},"NOT_MET")
    add("AST-string-literal", {"op":"eq","left":{"field":"label"},"right":{"literal":{"type":"string","value":"${7*7}<quote>"}}},
        {"label":"${7*7}<quote>"},"MET", fields=[{"path":"label","type":"string","sourceKind":"INPUT","required":False,"values":[],"minimum":None,"maximum":None}])
    exception = {"id":"na","when":cmp("gt",24),"outcome":"NOT_APPLICABLE","evidenceRefs":ir()["rules"][1]["evidenceRefs"]}
    add("AST-exception-na",cmp("lte"),{"months":25},"NOT_APPLICABLE",exceptions=[exception])
    review = {**exception,"id":"review","outcome":"REVIEW_REQUIRED"}
    add("AST-exception-priority",cmp("lte"),{"months":25},"REVIEW_REQUIRED",exceptions=[exception,review])
    return models, cases
