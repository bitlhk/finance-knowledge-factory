"""Parse a public regulation HTML snapshot, without inventing PDF page numbers."""

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
import urllib.request
import uuid

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from lxml import html

URL = "https://credit.mot.gov.cn/zhengcefagui/202408/t20240807_4147084.html"
CHECKS = ["第八条", "第三十三条", "第三十六条", "第四十三条", "第五十一条"]


def main():
    root = Path(".m1-local/documents") / uuid.uuid4().hex
    root.mkdir(parents=True)
    with urllib.request.urlopen(URL, timeout=45) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("DOCUMENT_SIZE_LIMIT")
    source = root / "regulation.html"
    source.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    tree = html.fromstring(raw.decode("utf-8"))
    started = time.monotonic()
    result = DocumentConverter(allowed_formats=[InputFormat.HTML]).convert(source)
    document = result.document.export_to_dict()
    (root / "docling.json").write_text(json.dumps(document, ensure_ascii=False, indent=2))
    nodes = tree.xpath("//p")
    evidence = []
    for text in document.get("texts", []):
        value = text.get("text", "")
        # Exact normalized paragraph matching; ambiguity stays explicit.
        normalize = lambda s: "".join(s.split())
        matches = [n for n in nodes if normalize("".join(n.itertext())) == normalize(value)]
        evidence.append({"text": value, "doclingRef": text.get("self_ref"),
                         "nativeProvenance": text.get("prov", []), "sourceDigest": sha,
                         "sourceXpaths": [tree.getroottree().getpath(n) for n in matches],
                         "locatorStatus": "EXACT_PARAGRAPH" if len(matches) == 1 else "AMBIGUOUS" if matches else "UNMAPPED",
                         "page": None})
    checks = [{"clause": label, "found": any(e["text"].lstrip().startswith(label) for e in evidence),
               "exactLocation": any(e["text"].lstrip().startswith(label) and e["locatorStatus"] == "EXACT_PARAGRAPH" for e in evidence)}
              for label in CHECKS]
    report = {"phase": "M1_HTML_PARSE_ONLY", "sourceUrl": URL, "sourceDigest": sha,
              "retrievedAt": datetime.now(timezone.utc).isoformat(),
              "parser": "docling-slim", "parserVersion": importlib.metadata.version("docling-slim"),
              "parseStatus": str(result.status), "elapsedSeconds": round(time.monotonic() - started, 3),
              "checks": checks, "textItems": len(evidence),
              "exactParagraphLocations": sum(e["locatorStatus"] == "EXACT_PARAGRAPH" for e in evidence),
              "ragflowCompared": False, "pdfTableCrossPageTested": False, "retrievalQuestionsTested": 0,
              "evidence": evidence}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "evidence"}, ensure_ascii=False, indent=2))
    print("Evidence:", root)


if __name__ == "__main__":
    main()
