"""Probe-only bridge: derived text lines are NOT lines in the original HTML.

The content-addressed sidecar must accompany every legacy IR evidence reference.
This does not change M0 or make its publisher understand native anchors.
"""
import hashlib

from knowledge_core.contracts import Rejected, digest, text_digest, validate
from knowledge_core.evidence.html_evidence import verify


VERSION = "html-anchor-bridge.v0.1"


def select_quote(raw, chunk, quote):
    """Explicit bounded extraction, retaining native offsets and the parent identity."""
    if not verify(raw, chunk) or not quote or "\n" in quote:
        raise Rejected("SUBCLAUSE_SELECTION_INVALID")
    matches = [a for a in chunk["anchors"] if a["quote"].count(quote) == 1]
    if len(matches) != 1 or sum(a["quote"].count(quote) for a in chunk["anchors"]) != 1:
        raise Rejected("SUBCLAUSE_NOT_UNIQUE")
    parent = matches[0]
    start = parent["start"] + parent["quote"].index(quote)
    selected = {"sourceDigest": chunk["sourceDigest"], "clause": chunk["clause"], "text": quote,
                "anchors": [{"xpath": parent["xpath"], "start": start, "end": start + len(quote), "quote": quote}]}
    if not verify(raw, selected):
        raise Rejected("SUBCLAUSE_ANCHOR_INVALID")
    return selected


def build(raw, chunks, source_id):
    if not chunks or not all(verify(raw, c) for c in chunks):
        raise Rejected("ORIGINAL_ANCHOR_INVALID")
    lines, mappings = [], []
    for chunk in chunks:
        for anchor in chunk["anchors"]:
            # A DOM text node can contain several physical newlines. Preserve them;
            # mapping ranges refer only to this explicitly derived text artifact.
            quote = anchor["quote"]
            start = len(lines) + 1
            lines.extend(quote.splitlines())
            native = {"schemaVersion": "evidence-anchor.v0.1",
                      "sourceBytesDigest": hashlib.sha256(raw).hexdigest(),
                      "mediaType": "text/html", "locatorKind": "HTML_DOM_TEXT",
                      "locator": {k: anchor[k] for k in ("xpath", "start", "end")},
                      "quote": quote, "quoteDigest": text_digest(quote)}
            mappings.append({"anchorId": digest(native), "anchor": native,
                             "clause": chunk["clause"], "lineStart": start,
                             "lineEnd": len(lines)})
    content = "\n".join(lines)
    source = {"schemaVersion": "source-revision.v0.1", "id": source_id,
              "revision": 1, "mediaType": "text/plain", "content": content,
              "contentDigest": text_digest(content)}
    validate("source-revision", source)
    bridge = {"schemaVersion": VERSION, "sourceBytesDigest": hashlib.sha256(raw).hexdigest(),
              "derivedSourceDigest": digest(source), "lineSpace": "DERIVED_TEXT_ONLY",
              "producer": "html-dom-text-bridge-0.1", "mappings": mappings}
    if len({m["anchorId"] for m in mappings}) != len(mappings):
        raise Rejected("DUPLICATE_NATIVE_ANCHOR")
    return source, bridge


def verify_bridge(raw, source, bridge, expected_digest):
    if digest(bridge) != expected_digest or bridge["schemaVersion"] != VERSION:
        raise Rejected("BRIDGE_DIGEST_OR_VERSION_MISMATCH")
    validate("source-revision", source)
    if bridge["lineSpace"] != "DERIVED_TEXT_ONLY" or digest(source) != bridge["derivedSourceDigest"]:
        raise Rejected("DERIVED_SOURCE_MISMATCH")
    if text_digest(source["content"]) != source["contentDigest"]:
        raise Rejected("DERIVED_CONTENT_MISMATCH")
    if hashlib.sha256(raw).hexdigest() != bridge["sourceBytesDigest"]:
        raise Rejected("ORIGINAL_SOURCE_MISMATCH")
    lines = source["content"].splitlines()
    next_line, ids = 1, set()
    for mapping in bridge["mappings"]:
        a = mapping["anchor"]
        if (a["schemaVersion"] != "evidence-anchor.v0.1" or a["mediaType"] != "text/html"
                or a["locatorKind"] != "HTML_DOM_TEXT"
                or a["sourceBytesDigest"] != bridge["sourceBytesDigest"]
                or mapping["anchorId"] != digest(a) or digest(a) in ids
                or text_digest(a["quote"]) != a["quoteDigest"]):
            raise Rejected("NATIVE_ANCHOR_IDENTITY_MISMATCH")
        ids.add(digest(a))
        if (type(mapping["lineStart"]) is not int or type(mapping["lineEnd"]) is not int
                or mapping["lineStart"] != next_line
                or not mapping["lineStart"] <= mapping["lineEnd"] <= len(lines)):
            raise Rejected("DERIVED_LINE_COVERAGE_INVALID")
        quote = "\n".join(lines[mapping["lineStart"] - 1:mapping["lineEnd"]])
        if quote != a["quote"] or not verify(raw, {"sourceDigest": a["sourceBytesDigest"],
                "text": quote, "anchors": [{**a["locator"], "quote": quote}]}):
            raise Rejected("NATIVE_QUOTE_MISMATCH")
        next_line = mapping["lineEnd"] + 1
    if not ids or next_line != len(lines) + 1:
        raise Rejected("DERIVED_LINE_COVERAGE_INVALID")


def resolve(raw, source, bridge, expected_digest, reference):
    verify_bridge(raw, source, bridge, expected_digest)
    start, end = reference["lineStart"], reference["lineEnd"]
    lines = source["content"].splitlines()
    if (reference["sourceDigest"] != digest(source) or type(start) is not int
            or type(end) is not int or not 1 <= start <= end <= len(lines)
            or text_digest("\n".join(lines[start-1:end])) != reference["quoteDigest"]):
        raise Rejected("RULE_REFERENCE_MISMATCH")
    return [m["anchorId"] for m in bridge["mappings"]
            if m["lineStart"] <= end and m["lineEnd"] >= start]


def bind_rule_evidence(raw, source, bridge, rules):
    """Freeze all rule, exception and unresolved-reference mappings, not just happy paths."""
    rows = []
    for rule in rules["rules"]:
        refs = [("condition", r) for r in rule["evidenceRefs"]]
        refs += [("exception:" + e["id"], r) for e in rule["exceptions"] for r in e["evidenceRefs"]]
        refs += [("unresolved", u["evidenceRef"]) for u in rule["unresolved"]]
        for role, ref in refs:
            rows.append({"ruleId": rule["id"], "role": role, "reference": ref,
                         "anchorIds": resolve(raw, source, bridge, digest(bridge), ref)})
    return {"schemaVersion": "rule-evidence-binding.v0.1", "ruleIrDigest": digest(rules),
            "bridgeDigest": digest(bridge), "publicationAllowed": False, "bindings": rows}
