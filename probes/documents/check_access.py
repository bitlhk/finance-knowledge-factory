"""Negative local dataset probes; not Knowledge Core IAM or real SSO acceptance."""
import json
import uuid
import requests

from probes.documents.ragflow_client import BASE, Client, STATE


def count_calls():
    return len((STATE / "embedding-calls.jsonl").read_text().splitlines())


def main():
    dataset = json.loads((STATE / "dataset.json").read_text())["id"]
    client = Client("knowledge-m1-other@example.invalid")
    report = {"datasetId": dataset, "beforeEmbeddingCalls": count_calls(), "records": [],
              "scope": "RAGFLOW_LOCAL_DATASET_ONLY_NOT_CORE_IAM"}
    for name, session in [("separate-local-account", client.session), ("anonymous", requests.Session())]:
        response = session.post(BASE + "/retrieval", json={"dataset_ids": [dataset], "question": "期限"}, timeout=30)
        body = response.json()
        report["records"].append({"identity": name, "httpStatus": response.status_code, "response": body})
    report["afterEmbeddingCalls"] = count_calls()
    report["passed"] = (report["beforeEmbeddingCalls"] == report["afterEmbeddingCalls"]
                         and [r["response"].get("code") for r in report["records"]] == [403, 401]
                         and all(r["response"].get("data") is None for r in report["records"]))
    path = STATE / ("permission-" + uuid.uuid4().hex + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("Permission probe:", report["passed"], path)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
