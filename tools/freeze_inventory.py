"""Generate source/contract/gold digests, separate from timestamped test outputs."""

import json
from pathlib import Path

from knowledge_core.contracts import digest, text_digest
from tests.support import CASES, ir, source


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    files = sorted(root.glob("contracts/*.json")) + [root / "tests/fixtures/rule-cases.json", root / "tests/support.py"]
    inventory = {
        "baseline": "Knowledge Core V0.1 M0 candidate",
        "v15HtmlSha256": "a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80",
        "harnessReadOnlyBaseline": "e911c71bdd3404f450bf775f32ebe028f90fb475",
        "canonicalization": "UTF-8 JSON; sorted keys; compact separators; no floats; not RFC8785",
        "files": {str(path.relative_to(root)): text_digest(path.read_text()) for path in files},
        "syntheticAssets": {"creditSource": digest(source()), "faqSource": digest(source("faq")), "creditIR": digest(ir())},
        "frozenRuleAssertions": len(CASES),
        "retrievalGoldQuestions": 0,
        "note": "26 M0 reference assertions do not equal the full 60 engineering cases or 30 retrieval questions."
    }
    target = root / "evidence/frozen-inputs.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(inventory, indent=2) + "\n")
    print(str(target))
