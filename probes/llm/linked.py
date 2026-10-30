"""Probe extraction envelope with per-rule applicability and evidence bindings.

Structural validation is not semantic approval. No output is publishable here.
"""
import copy
import json
import re

from jsonschema import Draft202012Validator
from knowledge_core.contracts import EXPRESSION, EXPR, ID, SCOPE, STR, Rejected, arr, obj, digest, text_digest, validate
from knowledge_core.rules import validate_ir
from tests.support import ir

QUOTES = arr(STR, 1, 20)
SCHEMA = obj({"rules": arr(obj({
    "id": ID, "title": STR, "predicate": EXPR,
    "appliesWhen": {"anyOf": [EXPR, {"type": "null"}]},
    "scope": SCOPE, "quotes": QUOTES,
    "exceptions": arr(obj({"when": EXPR, "outcome": {"enum": ["REVIEW_REQUIRED", "NOT_APPLICABLE"]}, "quotes": QUOTES}), 0, 10),
    "unresolvedQuotes": arr(STR, 0, 20),
}), 1, 10)})
SCHEMA["$defs"] = {"expression": EXPRESSION}
FIELDS = [copy.deepcopy(ir()["fields"][3]),
          {"path":"category","type":"enum","sourceKind":"INPUT","required":False,"values":["A","B"],"minimum":None,"maximum":None}]
SCOPE_CONTEXT = copy.deepcopy(ir()["rules"][0]["scope"])


def decode_envelope(content):
    """Accept one complete JSON fence, never salvage/repair fragments or semantics."""
    if len(content)>100000:
        raise Rejected("MODEL_OUTPUT_TOO_LARGE")
    body=content.strip()
    format_name="JSON"
    fenced=re.fullmatch(r"```json\s*\n(.*)\n```",body,re.DOTALL)
    if fenced:
        body=fenced.group(1)
        format_name="SINGLE_JSON_FENCE"
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise Rejected("DUPLICATE_MODEL_KEY")
            result[key]=value
        return result
    return json.loads(body,object_pairs_hook=pairs),format_name


def source(text, source_id):
    return {"schemaVersion":"source-revision.v0.1","id":source_id,"revision":1,
            "mediaType":"text/plain","content":text,"contentDigest":text_digest(text)}


def convert(envelope, src, fields=FIELDS, scope=SCOPE_CONTEXT):
    # Bound before invoking the recursive JSON Schema validator.
    def depth(value, n=0):
        if n > 24:
            raise Rejected("EXTRACTION_TOO_DEEP")
        if isinstance(value, dict):
            for child in value.values(): depth(child,n+1)
        if isinstance(value, list):
            for child in value: depth(child,n+1)
    depth(envelope)
    validate("source-revision",src)
    if list(Draft202012Validator(SCHEMA).iter_errors(envelope)):
        raise Rejected("EXTRACTION_SCHEMA_INVALID")
    if src["contentDigest"] != text_digest(src["content"]):
        raise Rejected("SOURCE_DIGEST_MISMATCH")
    lines = src["content"].splitlines()
    def ref(quote):
        hits = [i for i,line in enumerate(lines) if quote in line]
        if len(hits) != 1:
            raise Rejected("QUOTE_NOT_UNIQUE_IN_SOURCE")
        line = hits[0]
        return {"sourceDigest":digest(src),"lineStart":line+1,"lineEnd":line+1,"quoteDigest":text_digest(lines[line])}
    rules = []
    for item in envelope["rules"]:
        if item["scope"] != scope:
            raise Rejected("UNCONFIRMED_SCOPE_CHANGE")
        refs = [ref(q) for q in item["quotes"]]
        exceptions = [{"id":f"exception-{i}","when":e["when"],"outcome":e["outcome"],
                       "evidenceRefs":[ref(q) for q in e["quotes"]]} for i,e in enumerate(item["exceptions"])]
        if item["appliesWhen"] is not None:
            exceptions.append({"id":"applicability","when":{"op":"not","arg":item["appliesWhen"]},
                               "outcome":"NOT_APPLICABLE","evidenceRefs":refs})
        rules.append({"id":item["id"],"title":item["title"],"scope":copy.deepcopy(scope),
                      "predicate":item["predicate"],"evidenceRefs":refs,"exceptions":exceptions,
                      "unresolved":[{"reason":q,"evidenceRef":ref(q)} for q in item["unresolvedQuotes"]],"onMissing":"UNKNOWN"})
    result = {"schemaVersion":"rule-ir.v0.1","id":src["id"]+"-rules","revision":1,"classification":"DEMO",
              "fields":copy.deepcopy(fields),"rules":rules}
    validate_ir(result)
    return result
