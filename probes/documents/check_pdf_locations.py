"""Verify RAGFlow's returned PDF rectangles against independent Poppler text.

No inferred page numbers and no semantic matching: mismatches stay unresolved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unicodedata

from lxml import etree


def normalized(value):
    return "".join(unicodedata.normalize("NFKC", value).split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("ingestion", type=Path)
    ap.add_argument("--docling", action="store_true")
    args = ap.parse_args()
    xml = subprocess.check_output(["pdftotext", "-bbox", str(args.source), "-"], timeout=30)
    tree = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
    pages = tree.xpath("//*[local-name()='page']")
    original = json.loads(args.ingestion.read_text())
    assert original["sourceDigest"] == hashlib.sha256(args.source.read_bytes()).hexdigest()
    rows = []
    chunks = original["chunks"]["chunks"] if not args.docling else []
    if args.docling:
        for item in original["document"]["texts"]:
            for number, prov in enumerate(item.get("prov", [])):
                box = prov["bbox"]
                page = prov["page_no"]
                if box["coord_origin"] != "BOTTOMLEFT":
                    raise ValueError("UNSUPPORTED_COORDINATE_SYSTEM")
                height = float(pages[page-1].get("height"))
                start, end = prov["charspan"]
                chunks.append({"chunk_id": item["self_ref"] + ":" + str(number),
                               "content_with_weight": item["text"][start:end],
                               "positions": [[page, box["l"], box["r"], height-box["t"], height-box["b"]]]})
    for chunk in chunks:
        regions = []
        for p, left, right, top, bottom in chunk.get("positions", []):
            if type(p) is not int or not 1 <= p <= len(pages):
                raise ValueError("NATIVE_PAGE_OUT_OF_RANGE")
            words = pages[p-1].xpath(".//*[local-name()='word']")
            selected = [w.text or "" for w in words if
                        left <= (float(w.get("xMin")) + float(w.get("xMax"))) / 2 <= right
                        and top <= (float(w.get("yMin")) + float(w.get("yMax"))) / 2 <= bottom]
            regions.append({"page": p, "bbox": [left, top, right, bottom],
                            "coordinateSystem": "PDF_POINTS_TOP_LEFT", "popplerText": " ".join(selected)})
        body = chunk["content_with_weight"]
        retrieved = " ".join(r["popplerText"] for r in regions)
        rows.append({"chunkId": chunk["chunk_id"], "content": body, "regions": regions,
                     "exactNormalizedContent": bool(regions) and normalized(body) == normalized(retrieved)})
    report = {"sourceBytesDigest": original["sourceDigest"], "parser": "Docling native PDF provenance" if args.docling else "RAGFlow native PDF positions",
              "verifier": subprocess.run(["pdftotext", "-v"], capture_output=True, text=True).stderr.splitlines()[0],
              "pageCount": len(pages), "rows": rows, "exact": sum(r["exactNormalizedContent"] for r in rows),
              "total": len(rows), "authorityActivationVerified": False}
    path = args.ingestion.with_name("pdf-location-review.json")
    with path.open("x") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2))
    print({k: v for k, v in report.items() if k != "rows"})


if __name__ == "__main__":
    main()
