"""Controlled upload adapter for CMB Wealth Management product 132112.

The adapter accepts the three official PDF byte streams through the workbench,
verifies their immutable digests, and derives a compact evidence document whose
quotes remain mapped to the original PDF pages. It is deliberately product
specific; it is not a claim of general PDF ingestion support.
"""
from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

from lxml import etree, html

from knowledge_core.contracts import Rejected, digest, text_digest
from knowledge_core.evidence.anchor_bridge import build as build_bridge
from knowledge_core.evidence.html_evidence import verify


REGISTRATION_ID = "cmbwm-132112-njcb-202610"
PRODUCT_ID = "cmbwm-zhaorui-tianli-daily-21-132112"
TITLE = "招银理财招睿添利日开21号固定收益类理财计划"

SOURCES = {
    "sales-documents": {
        "filename":"2026-10-12-sales-documents.pdf",
        "sha256":"a7a95114729a7d1f59a36152480f7627a8dc4694890709bf241946dfd2c3529d",
        "pages":74,
        "title":"产品销售文件",
        "version":"南京银行网站发布 2026-10-12",
        "url":"https://www.njcb.com.cn/njcb/2026-10/12/article_2026101209093753130.html",
    },
    "contract-adjustment": {
        "filename":"2026-10-12-contract-adjustment.pdf",
        "sha256":"0158bef21447655e51487efe8d3c6b72bb3768dfbda38edb8a3dccad5428e0d0",
        "pages":1,
        "title":"合同条款调整公告",
        "version":"南京银行网站发布 2026-10-12；公告载明 2026-09-29 生效",
        "url":"https://www.njcb.com.cn/njcb/2026-10/12/article_2026101209080529090.html",
    },
    "fee-discount": {
        "filename":"2026-10-30-fee-discount.pdf",
        "sha256":"8832ce776f37b79d75b39479e169441cabf3f5b5c0b0d891c47d37fd48a6fe19",
        "pages":1,
        "title":"阶段性费率优惠公告",
        "version":"南京银行网站发布 2026-10-30；优惠期 2026-11-01 至 2026-11-07",
        "url":"https://www.njcb.com.cn/njcb/2026-10/30/article_2026103009082333364.html",
    },
}

ARTICLE_LABELS = tuple("第" + value + "条" for value in (
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三"))

QUESTIONS = [
    ("该产品是什么类型，管理人风险评级是多少？", "第一条"),
    ("什么风险承受能力的投资者适合购买？", "第一条"),
    ("产品代码、登记编码和南京银行销售的份额代码是什么？", "第二条"),
    ("南京银行渠道对应哪个份额，最低申购金额是多少？", "第二条"),
    ("产品每个交易日都一定可以成功申购和赎回吗？", "第三条"),
    ("正常赎回的确认和到账安排是什么？", "第七条"),
    ("巨额赎回发生时是否一定暂停赎回？", "第六条"),
    ("单个投资者赎回超过产品总份额10%的部分如何处理？", "第六条"),
    ("部分赎回后余额很少时会如何处理？", "第五条"),
    ("申购费和赎回费为零是否代表没有其他费用？", "第九条"),
    ("固定管理费、托管费、销售服务费及其他可能费用分别是什么？", "第九条"),
    ("2026年11月1日至7日哪些份额享受固定管理费优惠？", "第十二条"),
    ("合同条款调整涉及什么机制，从何时生效？", "第十一条"),
    ("仅凭销售文件能否确认南京银行当前实际受理申购且仍有额度？", "第十三条"),
    ("能否向客户保证未来某日赎回到账？", "第七条"),
]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized(value: str) -> str:
    # PDF layout extraction inserts spaces between Chinese table characters.
    # Removing layout whitespace gives a stable searchable quote while the
    # page number and original byte digest remain the authoritative locator.
    return re.sub(r"\s+", "", value)


def decode_uploads(files: list[dict]) -> dict[str, bytes]:
    if not isinstance(files, list) or len(files) != len(SOURCES):
        raise Rejected("BUSINESS_SOURCE_SET_INCOMPLETE")
    decoded = {}
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"sourceId", "filename", "contentBase64"}
                or item.get("sourceId") not in SOURCES):
            raise Rejected("BUSINESS_SOURCE_UPLOAD_INVALID")
        source_id = item["sourceId"]
        expected = SOURCES[source_id]
        if item["filename"] != expected["filename"] or source_id in decoded:
            raise Rejected("BUSINESS_SOURCE_UPLOAD_INVALID")
        try:
            value = base64.b64decode(item["contentBase64"], validate=True)
        except Exception as exc:
            raise Rejected("BUSINESS_SOURCE_UPLOAD_INVALID") from exc
        if not value.startswith(b"%PDF-") or _sha(value) != expected["sha256"]:
            raise Rejected("BUSINESS_SOURCE_DIGEST_MISMATCH")
        decoded[source_id] = value
    if set(decoded) != set(SOURCES):
        raise Rejected("BUSINESS_SOURCE_SET_INCOMPLETE")
    return decoded


def _pdf_pages(value: bytes, expected_pages: int) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="kf-pdf-") as directory:
        path = Path(directory) / "source.pdf"
        path.write_bytes(value)
        info = subprocess.run(["pdfinfo", str(path)], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True).stdout
        match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
        if not match or int(match.group(1)) != expected_pages:
            raise Rejected("PDF_PAGE_COUNT_MISMATCH")
        result = []
        for page in range(1, expected_pages + 1):
            extracted = subprocess.run(
                ["pdftotext", "-f", str(page), "-l", str(page), "-layout",
                 "-enc", "UTF-8", str(path), "-"], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode("utf-8")
            text = _normalized(extracted)
            if not text:
                raise Rejected("PDF_PAGE_TEXT_MISSING", str(page))
            result.append(text)
        return result


def _segment(page: str, start: str, end: str | None = None) -> str:
    start = _normalized(start)
    end = _normalized(end) if end is not None else None
    begin = page.find(start)
    finish = len(page) if end is None else page.find(end, begin + len(start))
    if begin < 0 or finish < 0 or finish <= begin:
        raise Rejected("BUSINESS_SOURCE_MARKER_MISSING", start)
    value = page[begin:finish].strip()
    if len(value) < 20:
        raise Rejected("BUSINESS_SOURCE_QUOTE_INCOMPLETE", start)
    return value


def _anchor(source_id: str, page: int, quote: str) -> dict:
    return {"sourceId":source_id, "sourceDigest":SOURCES[source_id]["sha256"],
            "mediaType":"application/pdf", "locatorKind":"PDF_PAGE_TEXT",
            "page":page, "quote":quote, "quoteDigest":text_digest(quote)}


def build_bundle(values: dict[str, bytes]) -> dict:
    if set(values) != set(SOURCES) or any(_sha(values[key]) != SOURCES[key]["sha256"] for key in SOURCES):
        raise Rejected("BUSINESS_SOURCE_DIGEST_MISMATCH")
    pages = {key:_pdf_pages(values[key], meta["pages"]) for key, meta in SOURCES.items()}
    sales = pages["sales-documents"]
    evidence = [
        ("风险等级与适用投资者", [_anchor("sales-documents", 12,
            _segment(sales[11], "本理财计划为公募开放式", "本《风险揭示书》所揭示事项"))]),
        ("产品身份、份额与起点金额", [_anchor("sales-documents", 15,
            _segment(sales[14], "产品登记编码", "（二）交易规则"))]),
        ("开放日与巨额赎回概览", [_anchor("sales-documents", 16,
            _segment(sales[15], "本理财计划存续期内", "就期间分配而言"))]),
        ("到账安排与基础费率", [_anchor("sales-documents", 17,
            _segment(sales[16], "对于产品终止情形", "认购费"))]),
        ("部分赎回与申请确认", [_anchor("sales-documents", 33,
            _segment(sales[32], "(8) 投资者有权部分或全部赎回"))]),
        ("大额及巨额赎回", [_anchor("sales-documents", 34,
            _segment(sales[33], "(12) 对于单个投资者", "3）延缓支付赎回款项"))]),
        ("赎回确认与资金支付", [_anchor("sales-documents", 35,
            _segment(sales[34], "6. 申购、赎回程序", "7. 申购份额和赎回金额"))]),
        ("暂停赎回与延缓支付条件", [_anchor("sales-documents", 37,
            _segment(sales[36], "(2) 发生下列情形时", "理财计划估值"))]),
        ("完整费用范围", [
            _anchor("sales-documents", 43, _segment(sales[42], "理财计划费用")),
            _anchor("sales-documents", 44, _segment(sales[43], "6. 托管费", "保密")),
        ]),
        ("税费与信息披露", [_anchor("sales-documents", 45,
            _segment(sales[44], "理财计划税费", "信息披露"))]),
        ("合同条款调整", [_anchor("contract-adjustment", 1,
            pages["contract-adjustment"][0])]),
        ("阶段性固定管理费优惠", [_anchor("fee-discount", 1,
            pages["fee-discount"][0])]),
        ("实时销售事实边界", [_anchor("sales-documents", 15,
            _segment(sales[14], "D份额：浦发银行", "境内托")),
            _anchor("sales-documents", 16,
            _segment(sales[15], "本理财计划存续期内", "特定情形下"))]),
    ]
    document = etree.Element("html")
    etree.SubElement(etree.SubElement(document, "head"), "meta", charset="utf-8")
    body = etree.SubElement(document, "body")
    mappings = []
    for position, (label, anchors) in enumerate(evidence, 1):
        article = etree.SubElement(body, "article", {"data-source-section":label})
        paragraph = etree.SubElement(article, "p")
        paragraph.text = ARTICLE_LABELS[position - 1] + " "
        span = etree.SubElement(paragraph, "span")
        span.text = "\n".join(item["quote"] for item in anchors)
        mappings.append((ARTICLE_LABELS[position - 1], label, anchors))
    raw = etree.tostring(document, method="html", encoding="utf-8", doctype="<!doctype html>")
    tree = html.fromstring(raw)
    chunks, provenance_mappings, source_references = [], [], []
    for position, (clause, label, anchors) in enumerate(mappings, 1):
        node = tree.xpath(f"//article[{position}]/p/span/text()[1]")[0]
        quote = str(node)
        xpath = tree.getroottree().getpath(node.getparent()) + "/text()[1]"
        chunk = {"clause":clause, "text":quote, "sourceDigest":_sha(raw),
                 "anchors":[{"xpath":xpath, "start":0, "end":len(quote), "quote":quote}]}
        if not verify(raw, chunk):
            raise Rejected("DERIVED_HTML_ANCHOR_INVALID", clause)
        chunks.append(chunk)
        provenance_mappings.append({"clause":clause, "section":label,
                                    "derivedAnchor":chunk["anchors"][0],
                                    "originalAnchors":anchors})
        documents = {item["sourceId"] for item in anchors}
        titles = "；".join(SOURCES[key]["title"] for key in sorted(documents))
        versions = "；".join(SOURCES[key]["version"] for key in sorted(documents))
        source_references.append({"clause":clause, "displayLabel":label,
            "documentTitle":titles, "documentVersion":versions,
            "locators":[{key:item[key] for key in ("sourceId", "sourceDigest", "mediaType",
                "locatorKind", "page", "quoteDigest")} for item in anchors]})
    source, bridge = build_bridge(raw, chunks, PRODUCT_ID + "-source")
    provenance = {"schemaVersion":"business-source-provenance.v0.1", "productId":PRODUCT_ID,
        "sourceFiles":[{"sourceId":key, **{k:v for k,v in meta.items()
            if k in {"filename","sha256","pages","title","version","url"}}}
            for key,meta in SOURCES.items()], "derivedHtmlDigest":_sha(raw),
        "derivedSourceDigest":digest(source), "mappings":provenance_mappings}
    provenance["provenanceDigest"] = digest(provenance)
    return {"html":raw, "chunks":chunks, "source":source, "bridge":bridge,
            "provenance":provenance, "sourceReferences":source_references,
            "tests":[{"question":question, "expectedClause":clause}
                     for question,clause in QUESTIONS]}
