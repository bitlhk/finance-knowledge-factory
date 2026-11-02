"""Build the versioned AMSYLJ01 quality set without changing frozen v0.1."""
import argparse
from copy import deepcopy
import json
from pathlib import Path


GOLD_CHANGES = {
    "wm-002-c1-suitability": {
        "reason":"公开资料没有定义C1代码映射；产品要求与实时客户映射分开验收。",
        "requiredEvidence":["product-spec:风险揭示书/适合购买的投资者",
                            "product-spec:风险揭示书/产品风险级别"],
        "requiredFacts":["本产品风险级别为2：中低风险",
                         "本产品适合投资者不含谨慎型"],
    },
    "wm-006-minimum-subscription": {
        "reason":"第五部分第5项已同时包含首次和追加金额，移除重复证据要求。",
        "requiredEvidence":["product-spec:第五部分第5项"],
    },
}


def build(original, blind):
    cases, changes = [], []
    for source in original["cases"]:
        if source["caseId"] == "wm-018-version-change":
            continue
        item = deepcopy(source)
        change = GOLD_CHANGES.get(item["caseId"])
        if change:
            before = {key:deepcopy(item.get(key)) for key in change if key != "reason"}
            for key, value in change.items():
                if key != "reason":
                    item[key] = deepcopy(value)
            changes.append({"caseId":item["caseId"], "reason":change["reason"],
                            "before":before,
                            "after":{key:item[key] for key in before}})
        cases.append(item)
    cases.extend(deepcopy(blind["cases"]))
    return {
        "schemaVersion":"business-task-quality-set.v0.2",
        "id":"boc-wealth-manager-amsylj01-v0.2",
        "revision":1,
        "institution":original["institution"],
        "task":"客户经理服务准备与产品条款说明（独立改进验收）",
        "productId":original["productId"],
        "lineage":{"baselineId":original["id"], "blindSetId":blind["id"],
                   "excludedPlatformCases":["wm-018-version-change"]},
        "goldChanges":changes,
        "cases":cases,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
        default=Path("examples/business/customer-manager"))
    args = parser.parse_args()
    original = json.loads((args.root / "boc-wealth-manager-test-set-v0.1.json")
                          .read_text(encoding="utf-8"))
    blind = json.loads((args.root / "amsylj01/analysis/blind-business-cases-v0.1.json")
                       .read_text(encoding="utf-8"))
    result = build(original, blind)
    output = args.root / "amsylj01/analysis/boc-wealth-manager-test-set-v0.2.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


if __name__ == "__main__":
    main()
