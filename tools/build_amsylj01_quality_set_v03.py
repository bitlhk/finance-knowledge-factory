"""Append the pre-frozen closeout blind set without changing v0.2 cases."""
import argparse
from copy import deepcopy
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
        default=Path("examples/business/customer-manager/amsylj01/analysis"))
    args = parser.parse_args()
    prior_path = args.root / "boc-wealth-manager-test-set-v0.2.json"
    blind_path = args.root / "blind-business-cases-v0.2.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    if not blind.get("frozenBeforeImplementation"):
        raise ValueError("BLIND_SET_NOT_PRE_FROZEN")
    result = deepcopy(prior)
    result.update({
        "schemaVersion":"business-task-quality-set.v0.3",
        "id":"boc-wealth-manager-amsylj01-v0.3",
        "revision":1,
        "task":"客户经理服务准备与产品条款说明（业务质量收口验收）",
        "lineage":{
            "baselineId":prior["id"],
            "closeoutBlindSetId":blind["id"],
            "frozenV02CaseCount":len(prior["cases"]),
        },
        "cases":deepcopy(prior["cases"]) + deepcopy(blind["cases"]),
    })
    output = args.root / "boc-wealth-manager-test-set-v0.3.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


if __name__ == "__main__":
    main()
