from quality.retrieval_profiles import PROFILES, query_variants, rank, support_decision


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


def test_quality_profile_decomposes_comparison_without_adding_facts():
    variants = query_variants("五年说的是资料保存还是测评有效期？",
                              "DETERMINISTIC_FINANCIAL_V0_1")
    assert variants[0] == "五年说的是资料保存还是测评有效期？"
    assert any("资料保存" in value for value in variants[1:])
    assert any("评估有效期" in value for value in variants[1:])


def test_support_policy_rejects_unsupported_product_comparison_and_fee():
    assert not support_decision("哪款理财收益最高？", "禁止夸大产品收益。",
                                "EVIDENCE_SUPPORT_V0_1")[0]
    assert not support_decision("申请对账单手续费多少？", "应在客服窗口提交申请。",
                                "EVIDENCE_SUPPORT_V0_1")[0]


def test_quality_rank_prefers_explicit_definition_and_action():
    definition = [candidate(1, 5200, "机构应清晰界定产品范围"),
                  candidate(2, 4300, "本办法所称适当性管理，是指开展识别、匹配等活动")]
    assert rank("监管文件怎么界定适当性管理？", definition, "STRUCTURE_V0_2")[0]["rank"] == 2
    action = [candidate(1, 5000, "应向投保人告知产品基本信息"),
              candidate(2, 4800, "不具备适当性的，应当建议投保人终止投保")]
    assert rank("保险产品不匹配时首先怎么办？", action, "STRUCTURE_V0_2")[0]["rank"] == 2
