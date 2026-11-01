"""Verified structural model for original HTML bytes.

The original DOM is authoritative. Parser and retrieval text can prove coverage
of that source, but can never create source evidence on their own.
"""
from __future__ import annotations

import hashlib
import re

from lxml import html

from knowledge_core.contracts import canonical
from knowledge_core.document_quality import DOCUMENT_UNIT, text_digest, validate_object


NUMBER = r"[一二三四五六七八九十百零〇0-9]+"
ARTICLE = re.compile(rf"^(第{NUMBER}条)(?:\s|$)")
CHAPTER = re.compile(rf"^(第{NUMBER}章)(?:\s|$)")
SECTION = re.compile(rf"^(第{NUMBER}节)(?:\s|$)")
ATTACHMENT = re.compile(r"^(附件(?:\s*[一二三四五六七八九十百零〇0-9]+)?)(?:[：:\s]|$)")
ITEM = re.compile(r"^(（[一二三四五六七八九十百零〇0-9]+）|[一二三四五六七八九十百零〇0-9]+、)")


def normalize(text):
    return "".join(text.split())


def _anchor(tree, root, node, original, quote):
    parent = node.getparent()
    selector = root.getpath(parent) + ("/following-sibling::text()[1]" if node.is_tail else "/text()[1]")
    start = original.index(quote)
    anchor = {"xpath": selector, "start": start, "end": start + len(quote), "quote": quote}
    selected = tree.xpath(selector)
    if len(selected) != 1 or str(selected[0])[anchor["start"]:anchor["end"]] != quote:
        raise ValueError("SOURCE_ANCHOR_MISMATCH")
    return anchor


def _unit(source_digest, kind, label, title, title_path, parent_id, order, anchors):
    text = "\n".join(anchor["quote"] for anchor in anchors)
    identity = {"sourceDigest": source_digest, "kind": kind, "label": label,
                "titlePath": title_path, "order": order, "anchors": anchors}
    unit = {
        "unitId": hashlib.sha256(canonical(identity).encode()).hexdigest(),
        "kind": kind, "label": label, "title": title, "titlePath": title_path,
        "parentId": parent_id, "order": order, "text": text,
        "textDigest": text_digest(text), "sourceDigest": source_digest, "anchors": anchors,
    }
    validate_object(DOCUMENT_UNIT, unit, "DOCUMENT_UNIT_INVALID")
    return unit


def _title(quote, label):
    value = quote[len(label):].strip(" \t:：") if label else quote
    return value or None


def _number(value):
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if value.isdigit():
        return int(value)
    total = current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def analyze(raw, parser_texts=None):
    """Return canonical units and independent completeness diagnostics."""
    tree = html.fromstring(raw.decode("utf-8"), parser=html.HTMLParser(no_network=True))
    root = tree.getroottree()
    source_digest = hashlib.sha256(raw).hexdigest()
    containers = tree.xpath("//main") or tree.xpath("//body") or [tree]
    nodes = containers[0].xpath(".//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript)]")
    parser = [normalize(str(value)) for value in (parser_texts or []) if normalize(str(value))]
    units, records = [], []
    headings = {"CHAPTER": None, "SECTION": None, "ATTACHMENT": None}
    current_article = None
    substantive = parser_covered = 0
    structure_started = False

    def add_heading(kind, match, anchor):
        nonlocal current_article
        label = match.group(1)
        if kind == "CHAPTER":
            headings.update(CHAPTER=None, SECTION=None, ATTACHMENT=None)
        elif kind == "SECTION":
            headings["SECTION"] = None
        elif kind == "ATTACHMENT":
            headings.update(CHAPTER=None, SECTION=None, ATTACHMENT=None)
        parents = [value for value in headings.values() if value]
        unit = _unit(source_digest, kind, label, _title(anchor["quote"], label),
                     [value["text"] for value in parents],
                     parents[-1]["unitId"] if parents else None, len(units), [anchor])
        units.append(unit)
        headings[kind] = unit
        current_article = None
        return unit

    for node in nodes:
        original = str(node)
        quote = original.strip()
        if not quote:
            continue
        structural_match = (CHAPTER.match(quote) or SECTION.match(quote)
                            or ATTACHMENT.match(quote) or ARTICLE.match(quote))
        if not structure_started and not structural_match:
            # Publication metadata and document titles are not regulatory body
            # units. The first explicit structural marker starts coverage.
            continue
        structure_started = True
        substantive += 1
        anchor = _anchor(tree, root, node, original, quote)
        represented = not parser or any(normalize(quote) in value for value in parser)
        parser_covered += represented
        record = {"anchor": anchor, "represented": represented, "unitIds": []}
        records.append(record)

        matched = CHAPTER.match(quote)
        if matched:
            record["unitIds"].append(add_heading("CHAPTER", matched, anchor)["unitId"])
            continue
        matched = SECTION.match(quote)
        if matched:
            record["unitIds"].append(add_heading("SECTION", matched, anchor)["unitId"])
            continue
        matched = ATTACHMENT.match(quote)
        if matched:
            record["unitIds"].append(add_heading("ATTACHMENT", matched, anchor)["unitId"])
            continue
        matched = ARTICLE.match(quote)
        if matched:
            label = matched.group(1)
            parents = [value for value in headings.values() if value]
            current_article = _unit(source_digest, "ARTICLE", label, None,
                                    [value["text"] for value in parents],
                                    parents[-1]["unitId"] if parents else None,
                                    len(units), [anchor])
            units.append(current_article)
            record["unitIds"].append(current_article["unitId"])
            continue
        if current_article is None:
            continue

        item = ITEM.match(quote)
        child = _unit(source_digest, "ITEM" if item else "PARAGRAPH", item.group(1) if item else None,
                      None, current_article["titlePath"] + [current_article["label"]],
                      current_article["unitId"], len(units), [anchor])
        units.append(child)
        record["unitIds"].append(child["unitId"])
        current_article["anchors"].append(anchor)
        current_article["text"] += "\n" + quote
        current_article["textDigest"] = text_digest(current_article["text"])
        validate_object(DOCUMENT_UNIT, current_article, "DOCUMENT_UNIT_INVALID")

    articles = [unit for unit in units if unit["kind"] == "ARTICLE"]
    for article in articles:
        old = article["unitId"]
        identity = {key: article[key] for key in ("sourceDigest", "kind", "label", "titlePath", "order", "anchors")}
        article["unitId"] = hashlib.sha256(canonical(identity).encode()).hexdigest()
        for unit in units:
            if unit["parentId"] == old:
                unit["parentId"] = article["unitId"]
    duplicate_labels = sorted({unit["label"] for unit in articles
                               if sum(other["label"] == unit["label"] for other in articles) > 1})
    numbers = [_number(re.fullmatch(rf"第({NUMBER})条", unit["label"]).group(1)) for unit in articles]
    unique_numbers = sorted({number for number in numbers if number is not None})
    missing_numbers = list(range(unique_numbers[0], unique_numbers[-1] + 1)) if unique_numbers else []
    missing_numbers = [number for number in missing_numbers if number not in unique_numbers]
    legacy_labels = {unit["unitId"]: " / ".join(unit["titlePath"] + [unit["label"]])
                     if unit["label"] in duplicate_labels else unit["label"] for unit in articles}
    covered = sum(bool(record["unitIds"]) for record in records)
    report = {
        "sourceDigest": source_digest, "substantiveNodeCount": substantive,
        "coveredNodeCount": covered, "parserCoveredNodeCount": parser_covered,
        "structureCoverageBps": 10000 * covered // substantive if substantive else 0,
        "parserCoverageBps": 10000 * parser_covered // substantive if substantive else 0,
        "anchorAccuracyBps": 10000 if units and all(verify_unit(raw, unit) for unit in units) else 0,
        "duplicateArticleLabels": duplicate_labels,
        "missingArticleNumbers": missing_numbers,
        "unassignedQuotes": [record["anchor"]["quote"] for record in records if not record["unitIds"]],
        "parserMissingQuotes": [record["anchor"]["quote"] for record in records if not record["represented"]],
    }
    return {"units": units, "legacyLabels": legacy_labels, "report": report}


def locate(raw, parser_texts):
    """Legacy article adapter retained for document v0.1."""
    result = analyze(raw, parser_texts)
    if result["report"]["parserCoverageBps"] != 10000:
        return []
    return [{"clause": result["legacyLabels"][unit["unitId"]], "text": unit["text"],
             "anchors": unit["anchors"], "sourceDigest": unit["sourceDigest"]}
            for unit in result["units"] if unit["kind"] == "ARTICLE"]


def verify_unit(raw, unit):
    try:
        validate_object(DOCUMENT_UNIT, unit, "DOCUMENT_UNIT_INVALID")
    except Exception:
        return False
    identity = {key: unit[key] for key in ("sourceDigest", "kind", "label", "titlePath", "order", "anchors")}
    if unit["unitId"] != hashlib.sha256(canonical(identity).encode()).hexdigest():
        return False
    return verify(raw, {"sourceDigest": unit["sourceDigest"], "text": unit["text"],
                        "anchors": unit["anchors"]})


def verify(raw, chunk):
    if not chunk["anchors"] or not chunk["text"]:
        return False
    if hashlib.sha256(raw).hexdigest() != chunk["sourceDigest"]:
        return False
    tree = html.fromstring(raw.decode("utf-8"), parser=html.HTMLParser(no_network=True))
    for anchor in chunk["anchors"]:
        if type(anchor["start"]) is not int or type(anchor["end"]) is not int or not 0 <= anchor["start"] < anchor["end"]:
            return False
        selected = tree.xpath(anchor["xpath"])
        if len(selected) != 1 or str(selected[0])[anchor["start"]:anchor["end"]] != anchor["quote"]:
            return False
    return chunk["text"] == "\n".join(anchor["quote"] for anchor in chunk["anchors"])


def _ranges(source, candidate):
    if source in candidate:
        return [(0, len(source))]
    ranges = []
    for line in filter(None, (normalize(value) for value in candidate.splitlines())):
        if len(line) < 8:
            continue
        start = source.find(line)
        if start >= 0:
            ranges.append((start, start + len(line)))
    return ranges


def map_retrieval_chunks(units, chunks):
    """Map split retrieval chunks to canonical articles and prove union coverage."""
    articles = [unit for unit in units if unit["kind"] == "ARTICLE"]
    coverage = {unit["unitId"]: [] for unit in articles}
    mapped = []
    for chunk in chunks:
        text = normalize(chunk["text"])
        unit_ids, paths = [], []
        for unit in articles:
            ranges = _ranges(normalize(unit["text"]), text)
            if ranges:
                coverage[unit["unitId"]].extend(ranges)
                unit_ids.append(unit["unitId"])
                paths.append(unit["titlePath"] + [unit["label"]])
        if unit_ids:
            mapped.append({"chunkId": chunk["id"], "text": chunk["text"],
                           "textDigest": text_digest(chunk["text"]), "unitIds": unit_ids,
                           "titlePaths": paths})
    incomplete = []
    for unit in articles:
        length = len(normalize(unit["text"]))
        merged = []
        for start, end in sorted(coverage[unit["unitId"]]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        if sum(end - start for start, end in merged) != length:
            incomplete.append(unit["unitId"])
    return {"chunks": mapped, "incompleteUnitIds": incomplete,
            "coverageBps": 10000 * (len(articles) - len(incomplete)) // len(articles) if articles else 0}
