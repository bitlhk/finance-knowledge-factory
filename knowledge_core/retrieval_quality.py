"""Versioned deterministic retrieval policy used by admitted document products."""
import re


def _bigrams(value):
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value).casefold()
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


def query_variants(question, mode):
    if mode in (None, "NONE"):
        return [question]
    if mode != "DETERMINISTIC_FINANCIAL_V0_1":
        raise ValueError("UNKNOWN_QUERY_PLANNER")
    variants = [question]
    substitutions = (("界定", "所称 是指"), ("手机渠道", "互联网 线上方式"),
                     ("不匹配", "不具备适当性"), ("测评", "评估"),
                     ("资料不全", "信息缺失"), ("材料不全", "信息缺失"))
    expanded = question
    for source, target in substitutions:
        expanded = expanded.replace(source, target)
    if expanded != question:
        variants.append(expanded)
    if "还是" in question:
        left, right = question.split("还是", 1)
        shared = " ".join(re.findall(r"[一二三四五六七八九十百千万\d]+(?:年|月|日|级|次)", question))
        for part in (left, right):
            value = (shared + " " + part).strip(" ？?")
            if value and value not in variants:
                variants.append(value)
    return variants[:4]


def merge_candidates(candidate_groups):
    merged = {}
    for query_index, candidates in enumerate(candidate_groups):
        for rank_index, candidate in enumerate(candidates, 1):
            current = merged.get(candidate["id"])
            contribution = round(10000 / (20 + rank_index))
            if current is None:
                current = {**candidate, "fusionScoreBps": 0, "queryIndexes": []}
                merged[candidate["id"]] = current
            current["fusionScoreBps"] += contribution
            current["queryIndexes"].append(query_index)
            if (candidate.get("scoreBps") or 0) > (current.get("scoreBps") or 0):
                for key in ("scoreBps", "termScoreBps", "vectorScoreBps"):
                    current[key] = candidate.get(key)
    output = sorted(merged.values(), key=lambda item: (-item["fusionScoreBps"], item["rank"]))
    return [{**item, "rank": position} for position, item in enumerate(output, 1)]


def _shape_bonus(question, text):
    bonus = 0
    if re.search(r"几级|多少级|分几级|几(?:个)?(?:风险)?等级|多少(?:个)?(?:风险)?等级", question) and re.search(
            r"(?:一|二|三|四|五|六|七|八|九|十|\d)+级|等级由低到高至少", text):
        bonus += 3200
    if re.search(r"多久|几年|多少年|期限|哪一天|何时|什么时候", question) and re.search(
            r"(?:一|二|三|四|五|六|七|八|九|十|百|\d)+(?:年|月|日)", text):
        bonus += 900
    if "产品" in question and "产品" not in text:
        bonus -= 500
    if re.search(r"客户|投资者", question) and not re.search(r"客户|投资者", text):
        bonus -= 500
    return bonus


def rank(question, candidates, mode):
    if mode == "NONE":
        return candidates
    if mode not in ("STRUCTURE_V0_1", "STRUCTURE_V0_2"):
        raise ValueError("UNKNOWN_POST_RANK_MODE")
    variants = query_variants(question, "DETERMINISTIC_FINANCIAL_V0_1") if mode == "STRUCTURE_V0_2" else [question]
    query = _bigrams(variants[1] if len(variants) > 1 else question)
    ranked = []
    for candidate in candidates:
        text_tokens = _bigrams(candidate["text"])
        lexical = round(10000 * len(query & text_tokens) / len(query)) if query else 0
        base = candidate["scoreBps"] or 0
        bonus = _shape_bonus(question, candidate["text"])
        if mode == "STRUCTURE_V0_2":
            if re.search(r"界定|什么是|是指什么", question) and re.search(r"所称.{0,30}是指|是指", candidate["text"]):
                bonus += 1600
            if "手机渠道" in question and re.search(r"互联网|线上方式", candidate["text"]):
                bonus += 1500
            if re.search(r"先要|先应|首先", question) and re.search(r"应当建议.{0,30}终止", candidate["text"]):
                bonus += 1300
            if re.search(r"什么情况下|哪些情形|何种情形", question) and re.search(
                    r"(?:对于|有下列情形|符合.{0,20}条件).{0,160}(?:可以|可|能够).{0,40}(?:简化|免于|不再)",
                    candidate["text"]):
                bonus += 1200
        score = max(0, min(10000, round(base * 0.6 + lexical * 0.4) + bonus))
        ranked.append({**candidate, "postRankScoreBps": score})
    return sorted(ranked, key=lambda value: (-value["postRankScoreBps"], value["rank"]))


def support_decision(question, text, mode):
    if mode in (None, "NONE"):
        return True, "support policy disabled"
    if mode != "EVIDENCE_SUPPORT_V0_1":
        raise ValueError("UNKNOWN_SUPPORT_POLICY")
    normalized = re.sub(r"\s+", "", text)
    if re.search(r"哪款|哪个|哪一个|哪家", question) and re.search(r"最高|最低|最好|最优", question):
        supported = bool(re.search(r"(?:产品名称|名称为|分别为).{0,80}(?:最高|最低|排序|比较)", normalized))
        return supported, "comparative product request requires named comparative evidence"
    if re.search(r"几级|多少级|分几级", question):
        supported = bool(re.search(r"(?:至少包括|划分为|分为).{0,40}(?:一|二|三|四|五|六|七|八|九|十|\d)+级", normalized))
        return supported, "quantitative level request requires an explicit level statement"
    if re.search(r"多少(?:元|钱|费用|手续费)|收费|费用是多少|手续费", question):
        supported = bool(re.search(r"手续费|收费|费用|金额|人民币|(?:元|角|分)(?:。|；|，)", normalized))
        return supported, "monetary request requires explicit fee or amount evidence"
    if re.search(r"界定|什么是|是指什么", question):
        supported = bool(re.search(r"所称.{0,30}是指|是指", normalized))
        return supported, "definition request requires definitional evidence"
    return True, "evidence contains no unsupported answer-type conflict"


def trace_select(client, dataset_id, document_id, question, profile):
    questions = query_variants(question, profile.get("queryPlanner"))
    groups = [client.retrieve_candidates(dataset_id, document_id, value, profile["retrieval"])
              for value in questions]
    candidates = merge_candidates(groups) if len(groups) > 1 else groups[0]
    retrieved = candidates
    candidates = rank(question, candidates, profile["postRank"])
    ranked = candidates
    selected = []
    filtered = []
    for candidate in candidates:
        score = candidate.get("postRankScoreBps", candidate.get("scoreBps") or 0)
        supported, support_reason = support_decision(question, candidate["text"], profile.get("supportPolicy"))
        keep = score >= profile["selectionThresholdBps"] and supported
        filtered.append({**candidate, "qualityDecision":"KEEP" if keep else "REJECT",
                         "qualityReasons":[f"score {score} {'>=' if score >= profile['selectionThresholdBps'] else '<'} "
                                           f"threshold {profile['selectionThresholdBps']}", support_reason]})
        if keep:
            selected.append(candidate)
        if len(selected) == 3:
            # Keep recording rejected/retained candidates for a complete trace.
            continue
    return {"queryVariants":questions, "retrieved":retrieved, "ranked":ranked,
            "filtered":filtered, "selected":selected[:3]}


def select(client, dataset_id, document_id, question, profile):
    return trace_select(client, dataset_id, document_id, question, profile)["selected"]
