from quality.retrieval_profiles import PROFILES, rank


def candidate(rank_value, score, text):
    return {"rank": rank_value, "scoreBps": score, "text": text}


def test_baseline_profile_remains_exactly_current_configuration():
    assert PROFILES["baseline"]["retrieval"] == {
        "pageSize": 3, "knnTopK": 64, "knnCandidates": 128, "rerankCandidates": 64,
        "similarityThresholdBps": 0, "keywordWeightBps": 7000, "rerankerId": None}


def test_structural_rank_prefers_answer_shape_without_hardcoded_clause():
    values = [candidate(1, 5300, "划分风险等级应考虑投资方向、期限和杠杆"),
              candidate(2, 4700, "投资型产品风险等级由低到高至少包括一级至五级")]
    ranked = rank("投资产品风险有几级？", values, "STRUCTURE_V0_1")
    assert ranked[0]["rank"] == 2


def test_structural_rank_is_deterministic():
    values = [candidate(1, 4000, "相同文本"), candidate(2, 4000, "相同文本")]
    assert [item["rank"] for item in rank("问题", values, "STRUCTURE_V0_1")] == [1, 2]
