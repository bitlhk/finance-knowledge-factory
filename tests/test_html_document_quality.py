from lxml import html
import pytest

from knowledge_core.contracts import Rejected
from knowledge_core.evidence.html_evidence import analyze, locate, map_retrieval_chunks
from m2.pipeline import parse


def parser_texts(raw):
    tree = html.fromstring(raw.decode("utf-8"))
    return list(map(str, tree.xpath("//text()[not(ancestor::script) and not(ancestor::style)]")))


def test_structure_retains_title_path_items_and_attachment():
    raw = """<html><body><h1>制度标题</h1><h2>第一章 总则</h2><h3>第一节 范围</h3>
      <p>第一条 应当符合以下条件：</p><p>（一）条件甲；</p><p>补充说明。</p>
      <h2>附件一：检查表</h2><p>第一条 附件要求。</p></body></html>""".encode()
    result = analyze(raw, parser_texts(raw))
    kinds = [unit["kind"] for unit in result["units"]]
    assert kinds == ["CHAPTER", "SECTION", "ARTICLE", "ITEM", "PARAGRAPH", "ATTACHMENT", "ARTICLE"]
    articles = [unit for unit in result["units"] if unit["kind"] == "ARTICLE"]
    assert articles[0]["titlePath"] == ["第一章 总则", "第一节 范围"]
    assert articles[1]["titlePath"] == ["附件一：检查表"]
    assert result["legacyLabels"][articles[0]["unitId"]] == "第一章 总则 / 第一节 范围 / 第一条"
    assert result["legacyLabels"][articles[1]["unitId"]] == "附件一：检查表 / 第一条"
    assert result["report"]["structureCoverageBps"] == 10000
    assert result["report"]["anchorAccuracyBps"] == 10000
    assert all(unit["parentId"] == articles[0]["unitId"] for unit in result["units"]
               if unit["kind"] in ("ITEM", "PARAGRAPH"))


def test_missing_article_sequence_fails_closed_before_ingest():
    raw = "<html><body><p>第一条 第一项。</p><p>第三条 第三项。</p></body></html>".encode()
    result = analyze(raw, parser_texts(raw))
    assert result["report"]["missingArticleNumbers"] == [2]
    with pytest.raises(Rejected, match="HTML_ARTICLE_SEQUENCE_INCOMPLETE"):
        parse(raw)


def test_parser_omission_is_not_silently_dropped():
    raw = "<html><body><p>第一条 第一段。</p><p>第二段不得遗漏。</p></body></html>".encode()
    result = analyze(raw, ["第一条 第一段。"])
    assert result["report"]["parserCoverageBps"] == 5000
    assert result["report"]["parserMissingQuotes"] == ["第二段不得遗漏。"]
    assert locate(raw, ["第一条 第一段。"]) == []


def test_split_long_article_requires_union_coverage():
    raw = ("<html><body><p>第一条 " + "甲" * 40 + "。</p><p>" + "乙" * 40 + "。</p></body></html>").encode()
    result = analyze(raw, parser_texts(raw))
    article = next(unit for unit in result["units"] if unit["kind"] == "ARTICLE")
    first, second = article["text"].splitlines()
    partial = map_retrieval_chunks(result["units"], [{"id": "a", "text": first}])
    complete = map_retrieval_chunks(result["units"], [{"id": "a", "text": first}, {"id": "b", "text": second}])
    assert partial["coverageBps"] == 0
    assert partial["incompleteUnitIds"] == [article["unitId"]]
    assert complete["coverageBps"] == 10000
    assert complete["incompleteUnitIds"] == []
