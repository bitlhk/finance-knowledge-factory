"""Generate the fixed-gold probe input, then execute the actual Java engine."""

import copy
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid
import xml.etree.ElementTree as ET

from knowledge_core.contracts import text_digest
from knowledge_core.rules import evaluate
from probes.flowable.compiler import compile_rule, prepare
from probes.flowable.compiler import NS
from probes.flowable.differential import additional_cases
from tests.support import CASES, CONTEXT, ir


def generate():
    rules = ir()
    models = {rule["id"]: compile_rule(rules, rule["id"]) for rule in rules["rules"]}
    cases = []
    for case in CASES:
        host = {**CONTEXT.facts(), **case.get("host", {})}
        reference = evaluate(rules, case["ruleId"], case["inputs"], host)["decision"]
        assert reference == case["expected"], case["id"]
        model = models[case["ruleId"]]
        cases.append({"id": case["id"], "expected": case["expected"], "reference": reference,
                      "compiledDigest": model["compiledDigest"], **prepare(rules, case["ruleId"], case["inputs"], host, model)})
    changed = copy.deepcopy(rules)
    changed["revision"] = 2
    changed["rules"][1]["predicate"]["right"]["literal"]["value"] = 12
    newer = compile_rule(changed, "months")
    for name, rule_set, model, expected in [("PIN-OLD", rules, models["months"], "MET"),
                                            ("PIN-NEW", changed, newer, "NOT_MET")]:
        assert evaluate(rule_set, "months", {"months": 24}, CONTEXT.facts())["decision"] == expected
        cases.append({"id": name, "expected": expected, "reference": expected,
                      "compiledDigest": model["compiledDigest"], **prepare(rule_set, "months", {"months": 24}, CONTEXT.facts(), model)})
    extra_models, extra_cases = additional_cases()
    faults = []
    for kind in ("zero-hit", "multiple-hit"):
        tree = ET.fromstring(models["months"]["xml"])
        table = tree.find(f".//{{{NS}}}decisionTable")
        if kind == "zero-hit":
            for row in list(table.findall(f"{{{NS}}}rule"))[2:]:
                table.remove(row)
        else:
            duplicate = copy.deepcopy(table.findall(f"{{{NS}}}rule")[2])
            for node in duplicate.iter():
                if "id" in node.attrib:
                    node.attrib["id"] += "_duplicate"
            duplicate.find(f"{{{NS}}}outputEntry/{{{NS}}}text").text = '"NOT_MET"'
            table.append(duplicate)
        faults.append({"id":kind,"key":models["months"]["key"],"xml":ET.tostring(tree,encoding="unicode"),
                       "variables":prepare(rules,"months",{"months":6},CONTEXT.facts(),models["months"])["variables"]})
    faults.append({"id":"malformed-xml","key":"broken","xml":"<definitions>","variables":{}})
    return {"models": [*models.values(), newer, *extra_models], "cases": cases + extra_cases,"faults":faults,
            "goldDigest": text_digest((Path(__file__).parents[2] / "tests/fixtures/rule-cases.json").read_text())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, help="Previously generated, local probe request; never a published service")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = root / ".m1-local/flowable" / uuid.uuid4().hex
    output.mkdir(parents=True)
    request = output / "request.json"
    response = output / "response.json"
    request.write_text(json.dumps(json.loads(args.request.read_text()) if args.request else generate(), indent=2) + "\n")
    command = ["mvn", "-B", "-ntp", f"-Dmaven.repo.local={root / '.m1-local/maven'}",
               "-f", str(root / "probes/flowable/pom.xml"), "compile", "exec:java",
               "-Dexec.mainClass=probe.FlowableProbe", f"-Dexec.args={request} {response}"]
    env = {**os.environ, "MAVEN_OPTS": "-Xmx768m -XX:ActiveProcessorCount=2 -Dorg.slf4j.simpleLogger.defaultLogLevel=warn"}
    with (output / "build.log").open("w") as log:
        result = subprocess.run(command, env=env, timeout=600, stdout=log, stderr=subprocess.STDOUT)
    (output / "exit.json").write_text(json.dumps({"exitCode": result.returncode}))
    print("Evidence:", output)
    print("Exit:", result.returncode)
    raise SystemExit(result.returncode)
