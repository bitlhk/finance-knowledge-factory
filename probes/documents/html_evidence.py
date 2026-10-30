"""Shared structural locator for original HTML bytes, independent of parser brand."""
import hashlib
import re

from lxml import html

CLAUSE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+条(?:\s|$)")
CHAPTER = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+章(?:\s|$)")


def normalize(text):
    return "".join(text.split())


def locate(raw, parser_texts):
    tree = html.fromstring(raw.decode("utf-8"))
    root = tree.getroottree()
    source_sha = hashlib.sha256(raw).hexdigest()
    parsed = [normalize(t) for t in parser_texts]
    chunks, current = [], None
    for node in tree.xpath("//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript)]"):
        original = str(node)
        quote = original.strip()
        if not quote:
            continue
        match = CLAUSE.match(quote)
        if match:
            current = {"clause": match.group().strip(), "text": "", "anchors": [], "sourceDigest": source_sha}
            chunks.append(current)
        elif CHAPTER.match(quote) or quote.startswith(("政策文件：", "政策解读：")):
            current = None
        if current is None:
            continue
        # A chunk cannot invent text omitted by the actual parser output.
        if not any(normalize(quote) in text for text in parsed):
            current["incomplete"] = True
            continue
        parent = node.getparent()
        if node.is_tail:
            selector = root.getpath(parent) + "/following-sibling::text()[1]"
        else:
            selector = root.getpath(parent) + "/text()[1]"
        start = original.index(quote)
        anchor = {"xpath": selector, "start": start, "end": start + len(quote), "quote": quote}
        selected = tree.xpath(selector)
        if len(selected) != 1 or str(selected[0])[anchor["start"]:anchor["end"]] != quote:
            raise ValueError("SOURCE_ANCHOR_MISMATCH")
        current["anchors"].append(anchor)
        current["text"] += ("\n" if current["text"] else "") + quote
    return [c for c in chunks if c["anchors"] and not c.get("incomplete")]


def verify(raw, chunk):
    if not chunk["anchors"] or not chunk["text"]:
        return False
    if hashlib.sha256(raw).hexdigest() != chunk["sourceDigest"]:
        return False
    tree = html.fromstring(raw.decode("utf-8"))
    for anchor in chunk["anchors"]:
        if type(anchor["start"]) is not int or type(anchor["end"]) is not int or not 0 <= anchor["start"] < anchor["end"]:
            return False
        selected = tree.xpath(anchor["xpath"])
        if len(selected) != 1 or str(selected[0])[anchor["start"]:anchor["end"]] != anchor["quote"]:
            return False
    return chunk["text"] == "\n".join(a["quote"] for a in chunk["anchors"])
