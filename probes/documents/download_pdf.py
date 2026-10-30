"""Secondary publisher copy, for parsing only; NOT an authority activation receipt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import uuid

URL = "https://n1.sinaimg.cn/www/c24b74a7/20240202/3.pdf"


def main():
    with urllib.request.urlopen(URL, timeout=45) as response:
        raw = response.read(20_000_001)
        resolved = response.url
    if len(raw) > 20_000_000 or not raw.startswith(b"%PDF-"):
        raise SystemExit("NOT_BOUNDED_PDF")
    out = Path(".m1-local/multiformat") / uuid.uuid4().hex
    out.mkdir(parents=True)
    (out / "regulation.pdf").write_bytes(raw)
    receipt = {"url": URL, "resolvedUrl": resolved, "sourceDigest": hashlib.sha256(raw).hexdigest(),
               "bytes": len(raw), "retrievedAt": datetime.now(timezone.utc).isoformat(),
               "sourceClass": "SECONDARY_REPRODUCTION", "authorityActivationVerified": False,
               "sameContentAsHtmlVerified": False}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print("Evidence:", out)


if __name__ == "__main__":
    main()
