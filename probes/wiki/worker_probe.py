"""Single-page compilation probe reusing pinned upstream profile/prompt functions.

Not the upstream OpenJiuwen pipeline, publication manager or Agent workbench.
The transport is the existing managed DeepSeek connection. No public listener.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request


UPSTREAM_COMMIT = "cbbc609e5b8155a29c511b21ce412097e4c2e07a"
UPSTREAM_URL = "https://gitcode.com/wangkun_123/Knowledge_builder.git"
MAX_SOURCE = 12000
SOURCE = {"id": "synthetic-customer-service", "revision": 1, "synthetic": True,
          "lines": ["客服受理时间为工作日09:00至17:00。", "客户可通过服务柜台提交资料补正申请。",
                    "材料不完整时，客服人员一次性告知所需补充的材料。", "客服不作出授信、放款或投资收益保证。"]}
RECIPE = {"id": "wiki-single-page-probe", "revision": 1, "title": "客服资料补正说明",
          "tags": ["受理时间", "申请渠道", "资料补正", "服务边界"],
          "page": "concepts/customer-service.md", "sourceBudget": MAX_SOURCE,
          "publicationAllowed": False}


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def anchors(source):
    return [{"anchorId": f"S{i}", "sourceDigest": sha(source), "lineStart": i,
             "lineEnd": i, "quote": line, "quoteDigest": sha(line)}
            for i, line in enumerate(source["lines"], 1)]


def source_text(source):
    text = "\n".join(f"[{a['anchorId']}] {a['quote']}" for a in anchors(source))
    if len(text) > MAX_SOURCE:
        raise ValueError("SOURCE_BUDGET_EXCEEDED_NO_TRUNCATION")
    return text


def assess_page(body, source, finish_reason):
    errors = []
    if finish_reason != "stop":
        errors.append("MODEL_INCOMPLETE")
    if not body.strip().startswith("---\n") or not re.search(r"\n---\s*\n", body[4:]):
        errors.append("FRONTMATTER_MISSING")
    if "## 原文出处" not in body:
        errors.append("SOURCE_SECTION_MISSING")
    observed = set(re.findall(r"\[\[source:(S\d+)\]\]", body))
    expected = {a["anchorId"] for a in anchors(source)}
    if observed - expected:
        errors.append("UNKNOWN_ANCHOR")
    if expected - observed:
        errors.append("PARTIAL_SOURCE_COVERAGE")
    # This proves reference existence/coverage, not entailment of every generated claim.
    return {"structuralPassed": not errors, "errors": errors, "sourceCoverage": sorted(observed & expected),
            "semanticQuality": "REVIEW_REQUIRED", "publicationAllowed": False}


def load_upstream(root):
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != UPSTREAM_COMMIT:
        raise ValueError("UPSTREAM_COMMIT_MISMATCH")
    relative = "tools/wiki-build-agent/python/app/"
    files = [relative + f for f in ("__init__.py", "config.py", "profiles.py", "prompts.py")]
    # A matching HEAD alone is insufficient: reject changed tracked source bytes.
    identities = {}
    for filename in files:
        actual = (root / filename).read_bytes()
        fixed = subprocess.check_output(["git", "-C", str(root), "show", f"{UPSTREAM_COMMIT}:{filename}"])
        if actual != fixed:
            raise ValueError("UPSTREAM_SOURCE_CHANGED")
        identities[filename] = hashlib.sha256(actual).hexdigest()
    sys.path.insert(0, str(root / "tools/wiki-build-agent/python"))
    profiles = importlib.import_module("app.profiles")
    return profiles, identities


def write(path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("MODEL_REDIRECT_REFUSED")


def run(upstream, output):
    profiles, identities = load_upstream(upstream)
    output.mkdir(parents=True, exist_ok=False)
    profile = profiles.get_build_profile("generic")
    source = source_text(SOURCE)
    prompt = profiles.build_topic_user_message(profile, RECIPE["title"], "concepts", RECIPE["tags"],
                                               "本次仅生成一个客服说明页面；无其他页面。", source)
    prompt += "\n引用约定：引用原料行使用 [[source:S1]] 等真实行标识；全部原料行须在原文出处列出。不得虚构相关页面。"
    request = {"model": "deepseek-v4-flash", "temperature": 0.1, "top_p": 1, "max_tokens": 2048,
               "thinking": {"type": "disabled"}, "stream": False,
               "messages": [{"role": "system", "content": profile.topic_prompt}, {"role": "user", "content": prompt}]}
    frozen = {"source": SOURCE, "anchors": anchors(SOURCE), "recipe": RECIPE, "request": request,
              "upstreamCommit": UPSTREAM_COMMIT, "upstreamFiles": identities,
              "automaticRetries": 0, "publicationAllowed": False}
    write(output / "frozen.json", frozen)
    base, key = os.environ["OPENAI_BASE_URL"].rstrip("/"), os.environ["OPENAI_API_KEY"]
    if not base.startswith("https://") or os.environ["OPENAI_MODEL"] != request["model"] or not key:
        raise ValueError("MANAGED_CONNECTION_MISMATCH")
    started = time.monotonic()
    record = {"frozenDigest": sha(frozen), "cost": None}
    try:
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(request, ensure_ascii=False).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=180) as response:
            text = response.read(1_000_001).decode()
        if key in text or len(text) > 1_000_000:
            raise ValueError("UNSAFE_RESPONSE")
        data = json.loads(text)
        body = data["choices"][0]["message"]["content"]
        assessment = assess_page(body, SOURCE, data["choices"][0].get("finish_reason"))
        record.update(response=data, assessment=assessment, modelCall="COMPLETED")
        artifact = {"title": RECIPE["title"], "body": body, "sourceDigest": sha(SOURCE),
                    "anchors": anchors(SOURCE), "recipeDigest": sha(RECIPE),
                    "requestDigest": sha(request), "responseDigest": sha(data),
                    "model": data.get("model"), "status": "CANDIDATE_REVIEW_REQUIRED",
                    "topicRelations": [], "quality": assessment, "publicationAllowed": False}
        write(output / "candidate.json", artifact)
    except Exception as exc:
        record.update(modelCall="FAILED", errorType=type(exc).__name__)
    record["elapsedMilliseconds"] = round((time.monotonic() - started) * 1000)
    write(output / "record.json", record)
    print(json.dumps({"modelCall": record["modelCall"], "assessment": record.get("assessment"), "cost": None}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.upstream.resolve(), args.output)
