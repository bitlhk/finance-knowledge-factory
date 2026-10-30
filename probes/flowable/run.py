"""Generate the fixed-gold probe input, then execute the actual Java engine."""

import copy
import json
import os
from pathlib import Path
import subprocess
import uuid

from knowledge_core.contracts import text_digest
from knowledge_core.rules import evaluate
from probes.flowable.compiler import compile_rule, prepare
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
    return {"models": [*models.values(), newer], "cases": cases,
            "goldDigest": text_digest((Path(__file__).parents[2] / "tests/fixtures/rule-cases.json").read_text())}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    output = root / ".m1-local/flowable" / uuid.uuid4().hex
    output.mkdir(parents=True)
    request = output / "request.json"
    response = output / "response.json"
    request.write_text(json.dumps(generate(), indent=2) + "\n")
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
