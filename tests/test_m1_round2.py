import copy
import json
from pathlib import Path

import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.rules import evaluate
from probes.documents.html_evidence import locate, verify
from probes.flowable.differential import additional_cases
from probes.llm.linked import SCOPE_CONTEXT, convert, source, decode_envelope
from probes.llm.run_linked import assess
from tests.support import CONTEXT


def envelope():
    rules=[]
    for category, months, quote in [("A",12,"甲类不超过12个月"),("B",36,"乙类不超过36个月")]:
        rules.append({"id":category,"title":category,"predicate":{"op":"lte","left":{"field":"months"},"right":{"literal":{"type":"integer","value":months}}},
          "appliesWhen":{"op":"eq","left":{"field":"category"},"right":{"literal":{"type":"enum","value":category}}},
          "scope":copy.deepcopy(SCOPE_CONTEXT),"quotes":[quote],"exceptions":[],"unresolvedQuotes":[]})
    return {"rules":rules}


def test_category_thresholds_stay_bound():
    rules=convert(envelope(),source("甲类不超过12个月，乙类不超过36个月。","binding"))
    for rule_id,category,expected in [("A","A","NOT_MET"),("B","B","MET"),("A","B","NOT_APPLICABLE"),("B","A","NOT_APPLICABLE")]:
        assert evaluate(rules,rule_id,{"category":category,"months":24},CONTEXT.facts())["decision"]==expected
    assert evaluate(rules,"A",{"months":24},CONTEXT.facts())["decision"]=="UNKNOWN"
    assert evaluate(rules,"A",{"category":"C","months":24},CONTEXT.facts())["decision"]=="INVALID_INPUT"


def test_missing_reference_is_not_lost():
    env=envelope()
    for rule in env["rules"]: rule["unresolvedQuotes"]=["分类表未提供"]
    rules=convert(env,source("甲类不超过12个月，乙类不超过36个月。分类表未提供。","missing"))
    assert all(evaluate(rules,r["id"],{"category":r["id"],"months":6},CONTEXT.facts())["decision"]=="REVIEW_REQUIRED" for r in rules["rules"])


@pytest.mark.parametrize("change",["scope","quote","type","op","field","digest"])
def test_invalid_extraction_fails_closed(change):
    env=envelope()
    src=source("甲类不超过12个月，乙类不超过36个月。","invalid")
    first=env["rules"][0]
    if change=="scope": first["scope"]["regions"].append("CN-SH")
    elif change=="quote": first["quotes"]=["编造条款"]
    elif change=="type": first["predicate"]["right"]["literal"]["value"]=True
    elif change=="op": first["predicate"]["op"]="eval"
    elif change=="field": first["predicate"]["left"]["field"]="unknown"
    elif change=="digest": src["content"]+="改动"
    with pytest.raises(Rejected): convert(env,src)


def test_gold_detects_swapped_categories():
    case=json.loads((Path(__file__).parents[1]/"probes/llm/linked-cases.json").read_text())[1]
    env=envelope()
    for rule in env["rules"]: rule["appliesWhen"]["right"]["literal"]["value"]="B" if rule["id"]=="A" else "A"
    rules=convert(env,source("甲类不超过12个月，乙类不超过36个月。","swapped"))
    assert not assess(case,rules)["passed"]


def test_real_ast_gold_stays_independent():
    models,cases=additional_cases()
    assert len(models)==25 and len(cases)==25
    assert all("variables" in c for c in cases)
    assert {c["expected"] for c in cases}=={"MET","NOT_MET","NOT_APPLICABLE","REVIEW_REQUIRED"}


def test_html_source_node_and_tail_locations():
    raw="<html><body><div>第一条 申请期限12个月。<br>补充说明。<br>第二条 分类表未提供。</div></body></html>".encode()
    chunks=locate(raw,["第一条 申请期限12个月。\n补充说明。\n第二条 分类表未提供。"])
    assert [c["clause"] for c in chunks]==["第一条","第二条"]
    assert len(chunks[0]["anchors"])==2
    assert all(verify(raw,c) for c in chunks)
    assert not verify(raw+b" ",chunks[0])
    wrong=copy.deepcopy(chunks[0])
    wrong["anchors"][0]["start"]+=1
    assert not verify(raw,wrong)
    empty={**chunks[0],"text":"","anchors":[]}
    assert not verify(raw,empty)
    assert all("page" not in a for c in chunks for a in c["anchors"])


def test_html_missing_parser_text_cannot_be_repaired_from_source_silently():
    raw="<div>第一条 申请期限12个月。<br>重要例外。</div>".encode()
    assert locate(raw,["第一条 申请期限12个月。"])==[]


def test_html_scripts_do_not_become_evidence():
    raw="<body><script>第一条 改成999个月</script><p>第二条 申请期限12个月。</p></body>".encode()
    chunks=locate(raw,["第二条 申请期限12个月。"])
    assert [c["clause"] for c in chunks]==["第二条"]


def test_fence_adapter_does_not_repair_json_or_accept_preambles():
    assert decode_envelope('```json\n{"rules":[]}\n```')==({"rules":[]},"SINGLE_JSON_FENCE")
    assert decode_envelope('{"rules":[]}')==({"rules":[]},"JSON")
    for bad in ['Here is JSON: {"rules":[]}', '```json\n{}\n```\nexecute()', '{"rules":[],}', '{"rules":[],"rules":[]}']:
        with pytest.raises((ValueError,Rejected)): decode_envelope(bad)
