"""Bounded reference semantics for M0. NOT a Flowable execution backend."""

import operator
from datetime import date

from .contracts import Rejected, strict_date, validate


OPS = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt,
       "lte": operator.le, "gt": operator.gt, "gte": operator.ge}
SCOPE_KEYS = {"region": "regions", "institution": "institutions",
              "product": "products", "purpose": "purposes"}


def validate_scope(scope):
    begin = strict_date(scope["validFrom"])
    if scope["validTo"] is not None and strict_date(scope["validTo"]) <= begin:
        raise Rejected("INVALID_EFFECTIVE_INTERVAL")


def in_scope(scope, host):
    business_date = strict_date(host["business_date"])
    return (all(host[key] in scope[group] for key, group in SCOPE_KEYS.items())
            and host["timezone"] == scope["timezone"]
            and business_date >= strict_date(scope["validFrom"])
            and (scope["validTo"] is None or business_date < strict_date(scope["validTo"])))


def typed(value, field):
    kind = field["type"]
    if kind == "integer":
        if type(value) is not int:
            raise Rejected("INVALID_INPUT", field.get("path", "literal"))
        if field.get("minimum") is not None and value < field["minimum"]:
            raise Rejected("INVALID_INPUT", "below minimum")
        if field.get("maximum") is not None and value > field["maximum"]:
            raise Rejected("INVALID_INPUT", "above maximum")
    elif kind == "boolean":
        if type(value) is not bool:
            raise Rejected("INVALID_INPUT", "boolean required")
    elif kind == "date":
        return strict_date(value)
    elif kind in ("enum", "string"):
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise Rejected("INVALID_INPUT", "nonempty string required")
        if kind == "enum" and field.get("values") and value not in field["values"]:
            raise Rejected("INVALID_INPUT", "unknown enumeration")
    else:
        raise Rejected("UNSUPPORTED_TYPE", kind)
    return value


def field_refs(expression):
    refs = set()
    if isinstance(expression, dict):
        if set(expression) == {"field"}:
            refs.add(expression["field"])
        for child in expression.values():
            refs.update(field_refs(child))
    elif isinstance(expression, list):
        for child in expression:
            refs.update(field_refs(child))
    return refs


def validate_ir(ir):
    # Bound depth before recursive JSON Schema descent.
    def size(value, depth=0):
        if depth > 32:
            raise Rejected("UNSUPPORTED_COMPLEXITY")
        if isinstance(value, dict):
            return 1 + sum(size(v, depth + 1) for v in value.values())
        if isinstance(value, list):
            return 1 + sum(size(v, depth + 1) for v in value)
        return 1
    if size(ir) > 30000:
        raise Rejected("UNSUPPORTED_COMPLEXITY")
    validate("rule-ir", ir)
    fields = {field["path"]: field for field in ir["fields"]}
    if len(fields) != len(ir["fields"]):
        raise Rejected("DUPLICATE_FIELD")
    if len({r["id"] for r in ir["rules"]}) != len(ir["rules"]):
        raise Rejected("DUPLICATE_RULE")
    for field in fields.values():
        if field["type"] == "enum" and not field["values"]:
            raise Rejected("EMPTY_ENUM")
        if field["type"] != "enum" and field["values"]:
            raise Rejected("INVALID_FIELD_CONSTRAINT")
        low, high = field["minimum"], field["maximum"]
        if field["type"] != "integer" and (low is not None or high is not None):
            raise Rejected("INVALID_FIELD_CONSTRAINT")
        if low is not None and high is not None and low > high:
            raise Rejected("INVALID_FIELD_CONSTRAINT")

    def operand(spec):
        if "field" in spec:
            if spec["field"] not in fields:
                raise Rejected("UNKNOWN_FIELD", spec["field"])
            return fields[spec["field"]]
        literal = spec["literal"]
        typed(literal["value"], literal)
        return literal

    def compatible(left, right, ordered=False):
        if left["type"] != right["type"]:
            raise Rejected("TYPE_MISMATCH")
        if ordered and left["type"] not in ("integer", "date"):
            raise Rejected("ORDERING_NOT_SUPPORTED")
        if left["type"] == "enum":
            if "values" in left and "value" in right:
                typed(right["value"], left)
            if "values" in right and "value" in left:
                typed(left["value"], right)
            if "values" in left and "values" in right and left["values"] != right["values"]:
                raise Rejected("ENUM_DOMAIN_MISMATCH")

    def expression(node, depth, count):
        count[0] += 1
        if depth > 4 or count[0] > 64:
            raise Rejected("UNSUPPORTED_COMPLEXITY")
        op = node["op"]
        if op in OPS:
            compatible(operand(node["left"]), operand(node["right"]), op not in ("eq", "ne"))
        elif op in ("all", "any"):
            for arg in node["args"]:
                expression(arg, depth + 1, count)
        elif op == "not":
            expression(node["arg"], depth + 1, count)
        elif op == "in":
            field = operand(node["value"])
            for item in node["set"]:
                compatible(field, operand({"literal": item}))
        elif op == "years_at_least":
            start, end = operand(node["start"]), operand(node["asOf"])
            if start["type"] != "date" or end["type"] != "date" or end["sourceKind"] != "HOST":
                raise Rejected("TRUSTED_DATE_REQUIRED")
    for rule in ir["rules"]:
        scope = rule["scope"]
        validate_scope(scope)
        count = [0]
        expression(rule["predicate"], 1, count)
        if len({e["id"] for e in rule["exceptions"]}) != len(rule["exceptions"]):
            raise Rejected("DUPLICATE_EXCEPTION")
        for exception in rule["exceptions"]:
            expression(exception["when"], 1, count)
    return ir


def evaluate(ir, rule_id, inputs, host):
    validate_ir(ir)
    rules = {rule["id"]: rule for rule in ir["rules"]}
    if rule_id not in rules:
        raise Rejected("UNKNOWN_RULE", rule_id)
    rule = rules[rule_id]
    fields = {field["path"]: field for field in ir["fields"]}
    values = {}
    def result(decision, missing=None):
        return {"decision": decision, "ruleId": rule_id, "missing": sorted(missing or []),
                "engine": "m0-reference-0.1.0"}
    if not isinstance(inputs, dict) or not isinstance(host, dict):
        return result("INVALID_INPUT")
    try:
        for key, value in inputs.items():
            if key not in fields or fields[key]["sourceKind"] != "INPUT":
                raise Rejected("INVALID_INPUT", "unrecognized or host-only input")
        for key, field in fields.items():
            source = inputs if field["sourceKind"] == "INPUT" else host
            if key in source and source[key] is not None:
                values[key] = typed(source[key], field)
        business_date = strict_date(host["business_date"]) if host.get("business_date") is not None else None
        for key in (*SCOPE_KEYS, "timezone"):
            if host.get(key) is not None and not isinstance(host[key], str):
                raise Rejected("INVALID_INPUT", key)
    except Rejected:
        return result("INVALID_INPUT")
    missing_context = [key for key in (*SCOPE_KEYS, "timezone", "business_date") if host.get(key) is None]
    if missing_context:
        return result("UNKNOWN", missing_context)
    scope = rule["scope"]
    if not in_scope(scope, host):
        return result("NOT_APPLICABLE")
    if rule["unresolved"]:
        return result("REVIEW_REQUIRED")
    refs = field_refs(rule["predicate"])
    for exception in rule["exceptions"]:
        refs.update(field_refs(exception["when"]))
    refs.update(key for key, field in fields.items() if field["required"])
    missing = refs - values.keys()
    if missing:
        return result("UNKNOWN", missing)

    def value(operand):
        return values[operand["field"]] if "field" in operand else typed(operand["literal"]["value"], operand["literal"])

    def run(node):
        op = node["op"]
        if op in OPS:
            return OPS[op](value(node["left"]), value(node["right"]))
        if op == "all":
            return all(run(arg) for arg in node["args"])
        if op == "any":
            return any(run(arg) for arg in node["args"])
        if op == "not":
            return not run(node["arg"])
        if op == "in":
            return value(node["value"]) in [typed(item["value"], item) for item in node["set"]]
        start, as_of = value(node["start"]), value(node["asOf"])
        year = start.year + node["years"]
        if year > 9999:
            raise Rejected("INVALID_INPUT", "anniversary out of range")
        try:
            anniversary = date(year, start.month, start.day)
        except ValueError:
            anniversary = date(year, 2, 28)
        return as_of >= anniversary
    try:
        matches = [e["outcome"] for e in rule["exceptions"] if run(e["when"])]
        if matches:
            return result("REVIEW_REQUIRED" if "REVIEW_REQUIRED" in matches else "NOT_APPLICABLE")
        return result("MET" if run(rule["predicate"]) else "NOT_MET")
    except Rejected:
        return result("INVALID_INPUT")
