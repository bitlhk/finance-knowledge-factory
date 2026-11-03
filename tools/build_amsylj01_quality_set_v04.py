"""Append the pre-frozen final blind set without changing v0.3 cases."""
import argparse
from copy import deepcopy
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("examples/business/customer-manager/amsylj01/analysis"),
    )
    args = parser.parse_args()
    prior_path = args.root / "boc-wealth-manager-test-set-v0.3.json"
    blind_path = args.root / "blind-business-cases-v0.3.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    if not blind.get("frozenBeforeImplementation"):
        raise ValueError("BLIND_SET_NOT_PRE_FROZEN")
    result = deepcopy(prior)
    result.update(
        {
            "schemaVersion": "business-task-quality-set.v0.4",
            "id": "boc-wealth-manager-amsylj01-v0.4",
            "revision": 1,
            "task": "客户经理服务准备与产品条款说明（最终业务质量验收）",
            "lineage": {
                "baselineId": prior["id"],
                "finalBlindSetId": blind["id"],
                "frozenV03CaseCount": len(prior["cases"]),
            },
            "cases": deepcopy(prior["cases"]) + deepcopy(blind["cases"]),
        }
    )
    output = args.root / "boc-wealth-manager-test-set-v0.4.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
