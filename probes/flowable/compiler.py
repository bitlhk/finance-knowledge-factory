"""Probe-only IR compiler: guarded typed inputs, generated JUEL, no rule fallback."""

from datetime import date
import xml.etree.ElementTree as ET

from knowledge_core.contracts import Rejected, digest, strict_date, text_digest
from knowledge_core.rules import SCOPE_KEYS, field_refs, in_scope, typed, validate_ir

NS = "http://www.omg.org/spec/DMN/20151101"
ET.register_namespace("", NS)
OPERATORS = {"eq": "==", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


def compile_rule(ir, rule_id):
    validate_ir(ir)
    rule = next(r for r in ir["rules"] if r["id"] == rule_id)
    slots = []

    def slot(spec):
        key = "v" + str(len(slots))
        slots.append({"name": key, **spec})
        return key

    def operand(item):
        return slot(item)

    def expr(node):
        op = node["op"]
        if op in OPERATORS:
            return f"({operand(node['left'])} {OPERATORS[op]} {operand(node['right'])})"
        if op in ("all", "any"):
            joiner = " && " if op == "all" else " || "
            return "(" + joiner.join(expr(arg) for arg in node["args"]) + ")"
        if op == "not":
            return "(!" + expr(node["arg"]) + ")"
        if op == "in":
            left = operand(node["value"])
            return "(" + " || ".join(f"({left} == {operand({'literal': item})})" for item in node["set"]) + ")"
        if op == "years_at_least":
            anniversary = slot({"anniversary": node})
            return f"({operand(node['asOf'])} >= {anniversary})"
        raise Rejected("UNSUPPORTED_OP")

    def exceptions(outcome):
        expressions = [expr(e["when"]) for e in rule["exceptions"] if e["outcome"] == outcome]
        return "(" + " || ".join(expressions) + ")" if expressions else "false"

    predicates = [exceptions("REVIEW_REQUIRED"), exceptions("NOT_APPLICABLE"), expr(rule["predicate"])]
    key = "condition_" + text_digest(rule_id)[:12]
    def child(parent, name, attrs=None, text=None):
        result = ET.SubElement(parent, f"{{{NS}}}{name}", attrs or {})
        result.text = text
        return result
    root = ET.Element(f"{{{NS}}}definitions", {"id": "definition", "name": "M1 probe", "namespace": "urn:knowledge:m1"})
    decision = child(root, "decision", {"id": key, "name": "Condition only"})
    table = child(decision, "decisionTable", {"id": "table", "hitPolicy": "UNIQUE"})
    for index, expression in enumerate(predicates):
        input_node = child(table, "input", {"id": f"input{index}"})
        child(child(input_node, "inputExpression", {"id": f"expression{index}", "typeRef": "boolean"}), "text", text=expression)
    child(table, "output", {"id": "output", "name": "decision", "typeRef": "string"})
    rows = [("true", "-", "-", "REVIEW_REQUIRED"), ("false", "true", "-", "NOT_APPLICABLE"),
            ("false", "false", "true", "MET"), ("false", "false", "false", "NOT_MET")]
    for index, row in enumerate(rows):
        rule_node = child(table, "rule", {"id": f"row{index}"})
        for column, entry in enumerate(row[:3]):
            child(child(rule_node, "inputEntry", {"id": f"cell{index}_{column}"}), "text", text=entry)
        child(child(rule_node, "outputEntry", {"id": f"result{index}"}), "text", text='"' + row[3] + '"')
    xml = ET.tostring(root, encoding="unicode")
    # Reparse generated XML; raw identifiers/literals never become executable text.
    assert ET.fromstring(xml).find(f".//{{{NS}}}decisionTable").attrib["hitPolicy"] == "UNIQUE"
    model = {"key": key, "xml": xml, "dmnDigest": text_digest(xml), "irDigest": digest(ir),
             "ruleId": rule_id, "slots": slots, "compiler": "m1-probe-0.1"}
    # The XML is a parameterized program. Constants/bindings are part of identity.
    return {**model, "compiledDigest": digest(model)}


def prepare(ir, rule_id, inputs, host, compiled):
    """Only input/scope gates run here. Eligible predicate evaluation runs in DMN."""
    validate_ir(ir)
    if compiled != compile_rule(ir, rule_id):
        raise Rejected("COMPILED_BINDING_MISMATCH")
    rule = next(r for r in ir["rules"] if r["id"] == rule_id)
    fields = {f["path"]: f for f in ir["fields"]}
    values = {}
    if not isinstance(inputs, dict) or not isinstance(host, dict):
        return {"guard": "INVALID_INPUT"}
    try:
        for key in inputs:
            if key not in fields or fields[key]["sourceKind"] != "INPUT":
                raise Rejected("INVALID_INPUT")
        for key, field in fields.items():
            source = inputs if field["sourceKind"] == "INPUT" else host
            if source.get(key) is not None:
                values[key] = typed(source[key], field)
        if host.get("business_date") is not None:
            strict_date(host["business_date"])
        for key in (*SCOPE_KEYS, "timezone"):
            if host.get(key) is not None and not isinstance(host[key], str):
                raise Rejected("INVALID_INPUT")
    except Rejected:
        return {"guard": "INVALID_INPUT"}
    if any(host.get(key) is None for key in (*SCOPE_KEYS, "timezone", "business_date")):
        return {"guard": "UNKNOWN"}
    if not in_scope(rule["scope"], host):
        return {"guard": "NOT_APPLICABLE"}
    if rule["unresolved"]:
        return {"guard": "REVIEW_REQUIRED"}
    required = field_refs(rule["predicate"])
    for exception in rule["exceptions"]:
        required.update(field_refs(exception["when"]))
    required.update(key for key, field in fields.items() if field["required"])
    if required - values.keys():
        return {"guard": "UNKNOWN"}
    variables = {}
    try:
        for spec in compiled["slots"]:
            if "field" in spec:
                value = values[spec["field"]]
            elif "literal" in spec:
                value = typed(spec["literal"]["value"], spec["literal"])
            else:
                node = spec["anniversary"]
                start = values[node["start"]["field"]]
                year = start.year + node["years"]
                if year > 9999:
                    return {"guard": "INVALID_INPUT"}
                try:
                    value = date(year, start.month, start.day)
                except ValueError:
                    value = date(year, 2, 28)
            variables[spec["name"]] = value.toordinal() if isinstance(value, date) else value
    except (Rejected, KeyError):
        return {"guard": "INVALID_INPUT"}
    return {"variables": variables}
