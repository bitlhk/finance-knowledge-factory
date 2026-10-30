"""Offline decoder/IR assessment of retained answers; zero model calls, no overwrite."""
import argparse
import json
from pathlib import Path
import uuid

from knowledge_core.contracts import text_digest
from probes.flowable.compiler import compile_rule, prepare
from probes.llm.linked import convert, decode_envelope, source
from probes.llm.run_linked import assess
from tests.support import CONTEXT


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("run_dir",type=Path)
    args=ap.parse_args()
    frozen=json.loads((args.run_dir/"frozen.json").read_text())
    out=Path(".m1-local/linked-replay")/uuid.uuid4().hex
    out.mkdir(parents=True)
    models,checks,records={ },[],[]
    for case in frozen["cases"]:
        path=args.run_dir/(case["id"]+".json")
        original=json.loads(path.read_text())
        data=json.loads(original["responseBody"])
        content=data["choices"][0]["message"]["content"]
        envelope,fmt=decode_envelope(content)
        rules=convert(envelope,source(case["text"],case["id"]))
        assessment=assess(case,rules)
        record={"id":case["id"],"originalAttemptDigest":text_digest(path.read_text()),
                "originalExecution":original["execution"],"format":fmt,"strictJsonCompliant":fmt=="JSON",
                "responseModel":data.get("model"),"usage":data.get("usage"),"assessment":assessment,"ir":rules}
        records.append(record)
        for rule in rules["rules"]:
            model=compile_rule(rules,rule["id"])
            models[model["compiledDigest"]]=model
        for i,check in enumerate(assessment["evaluations"]):
            model=compile_rule(rules,check["ruleId"])
            checks.append({"id":case["id"]+"-"+str(i),"compiledDigest":model["compiledDigest"],"expected":check["expected"],
                           **prepare(rules,check["ruleId"],check["inputs"],CONTEXT.facts(),model)})
    report={"mode":"OFFLINE_FORMAT_ADAPTER_AND_IR_REPLAY","modelCalls":0,"publicationAllowed":False,
            "originalGoldDigest":frozen["goldDigest"],"records":records}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (out/"engine-request.json").write_text(json.dumps({"models":list(models.values()),"cases":checks,"faults":[]},ensure_ascii=False,indent=2))
    print("Evidence:",out)
    print("Retained answers:",len(records),"IR gold passed:",sum(r["assessment"]["passed"] for r in records),"engine cases:",len(checks))
    if not all(r["assessment"]["passed"] for r in records): raise SystemExit(1)


if __name__=="__main__": main()
