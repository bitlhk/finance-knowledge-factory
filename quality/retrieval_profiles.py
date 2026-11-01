"""Candidate profiles and deterministic structural ranking for experiments."""
import re

from m2.ragflow import BASELINE_RETRIEVAL


PROFILES = {
    "baseline": {"retrieval": BASELINE_RETRIEVAL, "postRank": "NONE", "selectionThresholdBps": 0},
    "expanded": {"retrieval": {**BASELINE_RETRIEVAL, "pageSize": 12},
                 "postRank": "NONE", "selectionThresholdBps": 0},
    "hybrid-50": {"retrieval": {**BASELINE_RETRIEVAL, "pageSize": 12, "keywordWeightBps": 5000},
                  "postRank": "NONE", "selectionThresholdBps": 0},
    "structure-v01": {"retrieval": {**BASELINE_RETRIEVAL, "pageSize": 12},
                      "postRank": "STRUCTURE_V0_1", "selectionThresholdBps": 3300},
    "structure-hybrid-50": {"retrieval": {**BASELINE_RETRIEVAL, "pageSize": 12,
                                           "keywordWeightBps": 5000},
                            "postRank": "STRUCTURE_V0_1", "selectionThresholdBps": 3800},
}


def _bigrams(value):
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value).casefold()
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


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
    if mode != "STRUCTURE_V0_1":
        raise ValueError("UNKNOWN_POST_RANK_MODE")
    query = _bigrams(question)
    ranked = []
    for candidate in candidates:
        text_tokens = _bigrams(candidate["text"])
        lexical = round(10000 * len(query & text_tokens) / len(query)) if query else 0
        base = candidate["scoreBps"] or 0
        score = max(0, min(10000, round(base * 0.6 + lexical * 0.4) + _shape_bonus(question, candidate["text"])))
        ranked.append({**candidate, "postRankScoreBps": score})
    return sorted(ranked, key=lambda value: (-value["postRankScoreBps"], value["rank"]))
