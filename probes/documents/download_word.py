"""Fetch the linked official Word source, preserve original bytes and retrieval receipt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin
import uuid

from lxml import html
import requests

URL = "https://jkq.jining.gov.cn/art/2024/2/27/art_71912_2722624.html"


def main():
    out = Path(".m1-local/multiformat") / uuid.uuid4().hex
    out.mkdir(parents=True)
    page = requests.get(URL, timeout=30)
    page.raise_for_status()
    matches = [urljoin(URL, x) for x in html.fromstring(page.content).xpath("//a/@href") if "filename=" in x and ".doc" in x]
    if len(matches) != 1:
        raise ValueError("OFFICIAL_ATTACHMENT_NOT_UNIQUE")
    r = requests.get(matches[0], timeout=45)
    r.raise_for_status()
    if len(r.content) > 5_000_000:
        raise ValueError("ATTACHMENT_TOO_LARGE")
    (out / "regulation.doc").write_bytes(r.content)
    receipt = {"pageUrl": URL, "attachmentUrl": matches[0], "resolvedUrl": r.url,
               "retrievedAt": datetime.now(timezone.utc).isoformat(),
               "sourceDigest": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
               "mediaType": r.headers.get("Content-Type"), "magicHex": r.content[:8].hex()}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(receipt)
    print("Evidence:", out)


if __name__ == "__main__":
    main()
