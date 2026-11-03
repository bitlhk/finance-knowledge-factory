"""Controlled source adapter for the BOC AMSYLJ01 acceptance product.

This is intentionally not a generic PDF ingestion framework. It verifies three
fixed official source byte streams, extracts an allow-listed set of business
evidence, and records how every derived HTML quote maps back to a PDF page or an
official HTML DOM text node.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from lxml import etree, html

from knowledge_core.contracts import Rejected, digest, text_digest
from knowledge_core.evidence.anchor_bridge import build as build_bridge
from knowledge_core.evidence.html_evidence import analyze, map_retrieval_chunks, verify
from knowledge_core.rules import validate_scope


PRODUCT_ID = "boc-wealth-service-amsylj01"
SOURCE_HASHES = {
    "product-spec": "ffd336f6eb5544900c700fa87f76511e7661563f705a1947ceb68a5999e7109e",
    "sales-agreement": "60dc1e97e6ec744b9e804316c9ccc0026b9caedf20a9ba6a62b00d58e9c989dd",
    "investor-rights": "96682c229889c377316cadb827f9a10d42e112f5c9e351f0ffdf80581d3562d7",
}
SOURCE_FILES = {
    "product-spec": "product-spec.pdf",
    "sales-agreement": "sales-agreement.html",
    "investor-rights": "investor-rights.html",
}
POPPLER_VERSION = "24.02.0"
SOURCE_METADATA = {
    "product-spec": {
        "title":"中银日积月累-收益累进（AMSYLJ01）产品说明书及风险揭示书",
        "version":"2025-02-28",
    },
    "sales-agreement": {
        "title":"中国银行股份有限公司个人客户自营理财产品协议书（2023年版）",
        "version":"2023-12-01",
    },
    "investor-rights": {
        "title":"中国银行股份有限公司个人客户理财产品投资者权益须知",
        "version":"2023-05-11",
    },
}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _read_sources(directory: Path) -> dict[str, bytes]:
    values = {key:(directory / filename).read_bytes()
              for key, filename in SOURCE_FILES.items()}
    if {key:_sha(value) for key, value in values.items()} != SOURCE_HASHES:
        raise Rejected("BUSINESS_SOURCE_DIGEST_MISMATCH")
    return values


def _poppler_version() -> str:
    result = subprocess.run(["pdftotext", "-v"], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    match = re.search(r"pdftotext version ([0-9.]+)", result.stdout)
    if not match or match.group(1) != POPPLER_VERSION:
        raise Rejected("PDF_CONVERTER_VERSION_MISMATCH")
    return match.group(1)


def _pdf_pages(path: Path) -> list[str]:
    _poppler_version()
    info = subprocess.run(["pdfinfo", str(path)], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True).stdout
    pages = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    if not pages or int(pages.group(1)) != 9:
        raise Rejected("PDF_PAGE_COUNT_MISMATCH")
    result = []
    for page in range(1, 10):
        extracted = subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout",
             "-enc", "UTF-8", str(path), "-"], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode("utf-8")
        normalized = _normalized(extracted)
        if not normalized:
            raise Rejected("PDF_PAGE_TEXT_MISSING", str(page))
        result.append(normalized)
    return result


def _between(text: str, start: str, end: str | None) -> str:
    if text.count(start) != 1:
        raise Rejected("BUSINESS_SOURCE_MARKER_AMBIGUOUS", start)
    begin = text.index(start)
    finish = len(text) if end is None else text.find(end, begin + len(start))
    if finish < 0 or finish <= begin:
        raise Rejected("BUSINESS_SOURCE_MARKER_MISSING", end or start)
    value = text[begin:finish].strip()
    if len(value) < 8:
        raise Rejected("BUSINESS_SOURCE_QUOTE_INCOMPLETE", start)
    return value


def _pdf_anchor(pages: list[str], page: int, start: str,
                end: str | None) -> dict:
    quote = _between(pages[page - 1], start, end)
    return {"sourceId":"product-spec", "sourceDigest":SOURCE_HASHES["product-spec"],
            "mediaType":"application/pdf", "locatorKind":"PDF_PAGE_TEXT",
            "page":page, "quote":quote, "quoteDigest":text_digest(quote)}


def _html_anchor(raw: bytes, source_id: str, marker: str) -> dict:
    tree = html.fromstring(raw)
    root = tree.getroottree()
    matches = [node for node in tree.xpath(
        "//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript)]")
        if marker in _normalized(str(node))]
    if len(matches) != 1:
        raise Rejected("BUSINESS_SOURCE_MARKER_AMBIGUOUS", marker)
    node = matches[0]
    quote = _normalized(str(node))
    xpath = root.getpath(node.getparent()) + (
        "/following-sibling::text()[1]" if node.is_tail else "/text()[1]")
    return {"sourceId":source_id, "sourceDigest":SOURCE_HASHES[source_id],
            "mediaType":"text/html", "locatorKind":"HTML_DOM_NORMALIZED_TEXT",
            "xpath":xpath, "quote":quote, "quoteDigest":text_digest(quote)}


def _evidence(sources: dict[str, bytes], pages: list[str]) -> list[dict]:
    pdf = lambda page, start, end=None: _pdf_anchor(pages, page, start, end)
    agreement = lambda marker: _html_anchor(sources["sales-agreement"],
                                             "sales-agreement", marker)
    rights = lambda marker: _html_anchor(sources["investor-rights"],
                                         "investor-rights", marker)
    return [
        {"clause":"product-spec:风险揭示书/产品风险级别",
         "anchors":[pdf(1, "风险级别", "适合购买的投资者")]},
        {"clause":"product-spec:风险揭示书/适合购买的投资者",
         "anchors":[pdf(1, "适合购买的投资者", "风险揭示内容")]},
        {"clause":"product-spec:风险揭示书/风险揭示内容",
         "anchors":[pdf(1, "风险揭示内容 市场风险", "最不利投资情形下")]},
        {"clause":"product-spec:产品说明书/产品基本信息/投资者类型",
         "anchors":[pdf(3, "投资者类型", "初次申购起点金额")]},
        {"clause":"product-spec:第一部分/初次申购起点金额",
         "anchors":[pdf(3, "初次申购起点金额 初次申购起点金额人民币", "第 1 页")]},
        {"clause":"product-spec:特别提示",
         "anchors":[pdf(3, "特别提示：", "下面产品评级和相关描述")]},
        {"clause":"product-spec:第一部分/产品费率",
         "anchors":[pdf(4, "产品费率", "预期年化投资收益率")]},
        {"clause":"product-spec:第一部分/预期年化投资收益率",
         "anchors":[pdf(4, "预期年化投资收益率 理财计划管理人", "交易日 在本理财计划")]},
        {"clause":"product-spec:产品基本信息/交易日",
         "anchors":[pdf(4, "交易日 在本理财计划", "申购扣款")]},
        {"clause":"product-spec:产品基本信息/交易日与赎回到账",
         "anchors":[pdf(4, "交易日 在本理财计划", "申购扣款"),
                    pdf(5, "赎回到账 T日赎回", "赎回规则")]},
        {"clause":"product-spec:产品基本信息/提前终止",
         "anchors":[pdf(5, "提前终止 理财客户无提前终止权", "税款 理财收益")]},
        {"clause":"product-spec:第三部分",
         "anchors":[pdf(6, "三、理财计划费用", "四、理财计划收益")]},
        {"clause":"product-spec:第五部分/申购和赎回",
         "anchors":[pdf(6, "五、申购和赎回", "第 4 页")]},
        {"clause":"product-spec:第五部分/受理时间与挂单时间",
         "anchors":[pdf(7, "2 受理时间及清算时间", "4 申购和赎回价格")]},
        {"clause":"product-spec:第五部分第5项",
         "anchors":[pdf(7, "5 申购和赎回的金额要求", "6 申购和赎回的费率")]},
        {"clause":"product-spec:第五部分第6项",
         "anchors":[pdf(7, "6 申购和赎回的费率", "7 大额赎回")]},
        {"clause":"product-spec:第五部分第7项",
         "anchors":[pdf(7, "7 大额赎回", "8 理财计划存续期内")]},
        {"clause":"sales-agreement:第一部分",
         "anchors":[agreement("本协议与《产品说明书》不一致的") ]},
        {"clause":"sales-agreement:第二部分",
         "anchors":[agreement("理财非存款、产品有风险"),
                    agreement("对自营理财产品本金及收益的约定") ]},
        {"clause":"sales-agreement:第四部分第一项",
         "anchors":[agreement("投资资金来源合法且为本人自有资金") ]},
        {"clause":"sales-agreement:第四部分第九项",
         "anchors":[agreement("个人客户风险测评有效期为一年") ]},
        {"clause":"investor-rights:风险提示",
         "anchors":[rights("为保护您的合法权益"),
                    rights("投资者不得使用贷款") ]},
        {"clause":"investor-rights:第二部分",
         "anchors":[rights("个人投资者在我行首次购买"),
                    rights("风险承受能力评估旨在帮助"),
                    rights("风险承受能力评估结果的有效期为12个月") ]},
        {"clause":"investor-rights:第三部分/风险等级对应关系",
         "anchors":[rights("我行根据投资者的不同情况"),
                    rights("我行根据风险匹配原则"),
                    rights("请您根据您的风险承受能力评估结果选择") ]},
    ]


def _article_label(position: int) -> str:
    values = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
              "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八",
              "十九", "二十", "二十一", "二十二", "二十三", "二十四")
    return "第" + values[position - 1] + "条"


def build_bundle(source_directory: Path) -> dict:
    sources = _read_sources(source_directory)
    pages = _pdf_pages(source_directory / SOURCE_FILES["product-spec"])
    evidence = _evidence(sources, pages)
    document = etree.Element("html")
    head = etree.SubElement(document, "head")
    etree.SubElement(head, "meta", charset="utf-8")
    body = etree.SubElement(document, "body")
    for position, item in enumerate(evidence, 1):
        article = etree.SubElement(body, "article", {"data-evidence-clause":item["clause"]})
        paragraph = etree.SubElement(article, "p")
        paragraph.text = _article_label(position) + " "
        span = etree.SubElement(paragraph, "span")
        span.text = "\n".join(anchor["quote"] for anchor in item["anchors"])
    raw = etree.tostring(document, method="html", encoding="utf-8",
                         doctype="<!doctype html>")
    tree = html.fromstring(raw)
    root = tree.getroottree()
    chunks = []
    mappings = []
    for position, item in enumerate(evidence, 1):
        nodes = tree.xpath(f"//article[{position}]/p/span/text()[1]")
        if len(nodes) != 1:
            raise Rejected("DERIVED_HTML_ANCHOR_MISSING", item["clause"])
        node = nodes[0]
        quote = str(node)
        xpath = root.getpath(node.getparent()) + "/text()[1]"
        core_clause = _article_label(position)
        chunk = {"clause":core_clause, "text":quote,
                 "sourceDigest":_sha(raw),
                 "anchors":[{"xpath":xpath, "start":0, "end":len(quote),
                             "quote":quote}]}
        if not verify(raw, chunk):
            raise Rejected("DERIVED_HTML_ANCHOR_INVALID", item["clause"])
        chunks.append(chunk)
        mappings.append({"clause":item["clause"], "coreClause":core_clause,
                         "derivedAnchor":chunk["anchors"][0],
                         "originalAnchors":item["anchors"]})
    source, bridge = build_bridge(raw, chunks, PRODUCT_ID + "-source")
    provenance = {
        "schemaVersion":"business-source-provenance.v0.1",
        "productId":PRODUCT_ID,
        "sourceFiles":[{"sourceId":key, "filename":SOURCE_FILES[key],
                        "sha256":SOURCE_HASHES[key]}
                       for key in SOURCE_FILES],
        "converter":{"id":"poppler-pdftotext-layout", "version":POPPLER_VERSION,
                     "pdfPageCount":len(pages),
                     "pageTextDigests":[text_digest(page) for page in pages]},
        "derivedHtmlDigest":_sha(raw),
        "derivedSourceDigest":digest(source),
        "mappings":mappings,
    }
    provenance["provenanceDigest"] = digest(provenance)
    return {"html":raw, "chunks":chunks, "source":source, "bridge":bridge,
            "provenance":provenance, "pdfPages":pages}


def verify_bundle(source_directory: Path, html_bytes: bytes,
                  provenance: dict) -> None:
    rebuilt = build_bundle(source_directory)
    if (rebuilt["html"] != html_bytes
            or rebuilt["provenance"] != provenance
            or provenance.get("provenanceDigest") != digest({
                key:value for key, value in provenance.items()
                if key != "provenanceDigest"})):
        raise Rejected("BUSINESS_SOURCE_PROVENANCE_MISMATCH")


def source_references(provenance: dict) -> list[dict]:
    """Return user-facing source positions without exposing synthetic ordinals."""
    output = []
    for mapping in provenance["mappings"]:
        original = mapping["originalAnchors"]
        source_ids = {item["sourceId"] for item in original}
        if len(source_ids) != 1:
            raise Rejected("BUSINESS_SOURCE_REFERENCE_AMBIGUOUS", mapping["clause"])
        source_id = next(iter(source_ids))
        metadata = SOURCE_METADATA[source_id]
        positions = []
        for item in original:
            position = {key:item[key] for key in
                        ("sourceId", "sourceDigest", "mediaType", "locatorKind",
                         "page", "xpath", "quoteDigest") if key in item}
            positions.append(position)
        location = mapping["clause"].split(":", 1)[1]
        pages = sorted({item["page"] for item in original if "page" in item})
        page_label = ("，PDF第" + "、".join(map(str, pages)) + "页") if pages else ""
        output.append({
            "clause":mapping["coreClause"],
            "displayLabel":f"{metadata['title']}，{location}{page_label}",
            "documentTitle":metadata["title"],
            "documentVersion":metadata["version"],
            "locators":positions,
        })
    return output


def compile_quality_set(business_set: dict, source_digest: str,
                        provenance: dict) -> dict:
    categories = {
        "DIRECT":"CANONICAL", "BUSINESS_PLUS_KNOWLEDGE":"PARAPHRASE",
        "LIMIT":"PARAPHRASE", "EXCEPTION":"PARAPHRASE",
        "CONFUSABLE":"CONFUSABLE", "PROHIBITION":"CONFUSABLE",
        "PRECEDENCE":"CONFUSABLE", "NO_ANSWER":"NO_ANSWER",
        "VERSION":"NO_ANSWER",
    }
    aliases = {item["clause"]:item["coreClause"]
               for item in provenance["mappings"]}
    cases = []
    for item in business_set["cases"]:
        business_evidence = list(item.get("requiredEvidence") or [])
        if set(business_evidence) - set(aliases):
            raise Rejected("BUSINESS_GOLD_EVIDENCE_MISSING", item["caseId"])
        evidence = [aliases[value] for value in business_evidence]
        facts = list(item.get("requiredFacts") or [])
        live = list(item.get("requiredLiveFacts") or [])
        category = categories[item["category"]]
        if item["caseId"] in {"wm-016-current-customer-rating",
                              "wm-017-current-yield"}:
            # These are evidence-backed limitations, not pure no-answer retrieval
            # cases. The original business gold remains unchanged.
            category = "CONFUSABLE"
            facts += ["需要核实" + value for value in live]
        cases.append({"caseId":item["caseId"], "category":category,
                      "question":item["question"], "expectedClauses":evidence,
                      "answerFacts":facts,
                      "forbiddenClaims":list(item.get("forbiddenClaims") or [])})
    quality_id = ("boc-wealth-manager-amsylj01-core-v0-1"
                  if business_set.get("id") == "boc-wealth-manager-amsylj01-v0.1"
                  else "boc-wealth-manager-amsylj01-core-v0-2")
    return {"schemaVersion":"document-quality-test-set.v0.1",
            "id":quality_id,
            "purpose":"BLIND_ACCEPTANCE", "sourceDigest":source_digest,
            "sourceTitle":business_set["task"], "cases":cases}


def produce_candidate(core, actor, bundle: dict, scope: dict,
                      business_set: dict, consumers: list[str], client) -> dict:
    """Create a normal document Candidate from the verified fixed bundle."""
    actor.require("artifact.produce")
    validate_scope(scope)
    raw = bundle["html"]
    structure = analyze(raw)
    report = structure["report"]
    if (report["structureCoverageBps"] != 10000
            or report["anchorAccuracyBps"] != 10000
            or report["parserCoverageBps"] != 10000
            or report["missingArticleNumbers"]):
        raise Rejected("BUSINESS_DERIVED_STRUCTURE_INCOMPLETE")
    if len(bundle["chunks"]) != len([unit for unit in structure["units"]
                                     if unit["kind"] == "ARTICLE"]):
        raise Rejected("BUSINESS_EVIDENCE_UNIT_MISMATCH")
    source = dict(bundle["source"])
    source_digest = core.register_source(actor, source)
    core._source_access(actor, source_digest)
    index = client.ingest(raw)
    mapped = map_retrieval_chunks(structure["units"], index["chunks"])
    if mapped["coverageBps"] != 10000 or mapped["incompleteUnitIds"]:
        raise Rejected("INDEX_COVERAGE_INCOMPLETE")
    articles = [unit for unit in structure["units"] if unit["kind"] == "ARTICLE"]
    labels = {unit["unitId"]:unit["label"] for unit in articles}
    mapped_by_id = {item["chunkId"]:item for item in mapped["chunks"]}
    for chunk in index["chunks"]:
        chunk["textDigest"] = text_digest(chunk["text"])
        chunk["clauses"] = []
        for unit_id in mapped_by_id.get(chunk["id"], {}).get("unitIds", []):
            clause = labels.get(unit_id)
            if clause and clause not in chunk["clauses"]:
                chunk["clauses"].append(clause)
    represented = {clause for chunk in index["chunks"] for clause in chunk["clauses"]}
    expected = {item["clause"] for item in bundle["chunks"]}
    if represented != expected:
        raise Rejected("BUSINESS_EVIDENCE_INDEX_INCOMPLETE")
    index_digest = core.register_document_index(
        actor, source_digest, raw, bundle["bridge"], index,
        [{"clause":item["clause"], "text":item["text"]}
         for item in bundle["chunks"]],
        source_references(bundle["provenance"]))
    lines = source["content"].splitlines()
    references = []
    for item in bundle["chunks"]:
        mappings = [mapping for mapping in bundle["bridge"]["mappings"]
                    if mapping["clause"] == item["clause"]]
        start, end = mappings[0]["lineStart"], mappings[-1]["lineEnd"]
        references.append({"sourceDigest":source_digest, "lineStart":start,
                           "lineEnd":end,
                           "quoteDigest":text_digest("\n".join(lines[start - 1:end]))})
    test_digest = core.register_test_set(actor, {
        "schemaVersion":"test-set.v0.1", "id":PRODUCT_ID + "-retrieval-tests",
        "revision":1, "ruleCases":[], "evidenceCases":references})
    recipe_digest = core.save_recipe(actor, {
        "schemaVersion":"recipe.v0.1", "id":PRODUCT_ID + "-recipe",
        "revision":1, "productId":PRODUCT_ID,
        "sourceDigests":[source_digest], "processes":["document"],
        "testSetDigest":test_digest, "intendedConsumers":consumers,
        "intendedHistoryReaders":consumers, "versionPolicy":"PINNED"}, 0)
    artifact_digest = core.register_artifact(actor, {
        "schemaVersion":"artifact.v0.1", "id":PRODUCT_ID + "-evidence",
        "revision":1, "kind":"evidence", "sourceDigests":[source_digest],
        "scope":scope, "evidence":references, "ruleSetDigest":None})
    core_candidate = core.create_candidate(actor, recipe_digest, [artifact_digest])
    aliases = {item["clause"]:item["coreClause"]
               for item in bundle["provenance"]["mappings"]}
    legacy = [{"question":item["question"],
               "expectedClause":aliases[item["requiredEvidence"][0]]}
              for item in business_set["cases"] if item.get("requiredEvidence")]
    candidate = core.create_document_candidate(
        actor, core_candidate, index_digest, legacy)
    quality = compile_quality_set(business_set, source_digest,
                                  bundle["provenance"])
    return {"sourceDigest":source_digest, "indexDigest":index_digest,
            "recipeDigest":recipe_digest, "artifactDigest":artifact_digest,
            "coreCandidateDigest":core_candidate, "candidateDigest":candidate,
            "qualityTestSet":quality,
            "provenanceDigest":bundle["provenance"]["provenanceDigest"]}


def write_bundle(source_directory: Path, business_set_path: Path,
                 output_directory: Path) -> dict:
    bundle = build_bundle(source_directory)
    business = json.loads(business_set_path.read_text(encoding="utf-8"))
    quality = compile_quality_set(business, digest(bundle["source"]),
                                  bundle["provenance"])
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "amsylj01-derived.html").write_bytes(bundle["html"])
    (output_directory / "amsylj01-provenance.json").write_text(
        json.dumps(bundle["provenance"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (output_directory / "amsylj01-pdf-pages.json").write_text(
        json.dumps(bundle["pdfPages"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (output_directory / "amsylj01-core-quality-set-v0.1.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**bundle, "qualityTestSet":quality}
