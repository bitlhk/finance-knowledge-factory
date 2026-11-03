from quality.retrieval_profiles import PROFILES, query_variants, rank, support_decision
from knowledge_core.retrieval_quality import _evidence_concepts, _select


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


def test_business_profile_decomposes_multi_intent_without_clause_ids():
    variants = query_variants(
        "某款理财的风险等级和适合客户类型是什么？",
        "DETERMINISTIC_FINANCIAL_V0_2")
    assert "产品风险级别 风险等级" in variants
    assert "适合购买的投资者 投资者类型 风险承受能力" in variants
    assert all("第一条" not in value for value in variants)


def test_customer_rating_question_retrieves_product_requirements_not_a_code_map():
    variants = query_variants("C1客户可以购买这款产品吗？",
                              "DETERMINISTIC_FINANCIAL_V0_2")
    assert "产品风险级别 适合购买的投资者" in variants


def test_diverse_selection_covers_independent_query_variants():
    candidates = [
        {"id":"general", "rank":1, "text":"风险匹配一般原则",
         "postRankScoreBps":7000, "queryIndexes":[0]},
        {"id":"risk", "rank":2, "text":"产品风险级别2中低风险",
         "postRankScoreBps":6500, "queryIndexes":[1]},
        {"id":"customer", "rank":3, "text":"适合购买的投资者类型",
         "postRankScoreBps":6400, "queryIndexes":[2]},
        {"id":"duplicate", "rank":4, "text":"另一段风险匹配一般原则",
         "postRankScoreBps":6900, "queryIndexes":[0]},
    ]
    selected = _select(candidates, 3, "DIVERSE_QUERY_COVERAGE_V0_1")
    assert {item["id"] for item in selected} == {"general", "risk", "customer"}


def test_business_concepts_are_derived_from_evidence_text_not_clause_ids():
    question = "这款产品风险等级和适合客户类型是什么？"
    assert _evidence_concepts(question, "风险级别 2：中低风险") == [
        "product-risk-level"]
    assert _evidence_concepts(question, "投资者类型：稳健型、平衡型") == [
        "suitable-investor"]
    assert _evidence_concepts(question, "我行将产品风险分为五级") == []


def test_redemption_concepts_keep_termination_and_normal_redemption_distinct():
    question = "客户三个月后用钱，是否可以提前赎回？"
    normal = _evidence_concepts(question, "每个交易日开放申购和赎回")
    termination = _evidence_concepts(question, "理财客户无提前终止权")
    arrival = _evidence_concepts(question, "T日赎回，本金和收益T+1日到账")
    assert normal == ["normal-redemption-opening", "normal-redemption"]
    assert termination == ["early-termination", "future-termination-distinction"]
    assert arrival == ["redemption-arrival"]


def test_fee_selection_keeps_zero_rates_and_other_charges_as_separate_evidence():
    question = "这款产品申购、赎回和管理费用如何收取？"
    zero = _evidence_concepts(question, "本理财计划无申购、赎回费。")
    charges = _evidence_concepts(question, "固定投资管理费率0.2%，可能发生其他税费。")
    assert "zero-subscription-redemption-fees" in zero
    assert "complete-fees" in charges


def test_complete_fee_scope_and_exact_order_window_are_independent_concepts():
    fee_question = "申购费和赎回费都是0，是否代表完全不收费？"
    fee_text = ("固定投资管理费0.2%，托管费0.03%，其他税费按实际发生额支付，"
                "并可能收取浮动投资管理费。")
    assert "full-fee-schedule" in _evidence_concepts(fee_question, fee_text)
    time_question = "客户周五15:40提交赎回，什么时候受理？"
    time_text = "受理时间8:30-15:30，挂单时间15:45-24:00。"
    assert "order-window" in _evidence_concepts(time_question, time_text)


def test_future_redemption_question_keeps_suspension_evidence():
    question = "客户三个月后用钱，届时能否赎回？"
    text = "发生流动性风险时，管理人有权暂停申购或赎回。"
    assert "redemption-suspension" in _evidence_concepts(question, text)
    timing = "投资者可在受理时间内提出赎回，赎回本金和收益T+1日到账。"
    assert "future-liquidity-timing" in _evidence_concepts(question, timing)
    termination = "理财客户无提前终止权。"
    assert "future-termination-distinction" in _evidence_concepts(
        question, termination)


def test_large_redemption_concept_includes_next_trading_day_handling():
    question = "发生大额赎回后还能提交申请吗？"
    text = "管理人有权暂停接受当日赎回申请，下一交易日继续接受赎回申请。"
    concepts = _evidence_concepts(question, text)
    assert "large-redemption" in concepts
    assert "large-redemption-followup" in concepts


def test_giant_redemption_and_product_fee_phrasing_are_recognized():
    redemption = _evidence_concepts(
        "发生巨额赎回时是否自动暂停？",
        "发生巨额赎回时，管理人有权选择全额赎回、部分赎回或延缓支付。")
    assert "large-redemption" in redemption
    partial = _evidence_concepts(
        "部分赎回后剩余份额不足0.01份怎么办？",
        "投资者剩余份额将被一次性全额赎回。")
    assert "partial-redemption" in partial
    fees = _evidence_concepts(
        "申购费和赎回费为零是否代表没有其他费用？",
        "投资者无需支付申购费，投资者无需支付赎回费。")
    assert "zero-subscription-redemption-fees" in fees


def test_specific_redemption_and_complete_fee_evidence_outrank_summaries():
    giant = rank("发生巨额赎回时可以采取哪些措施？", [
        candidate(1, 8000, "巨额赎回时可能延缓支付。"),
        candidate(2, 7000, "巨额赎回的处理方式包括全额赎回、部分赎回或延缓支付。"),
    ], "STRUCTURE_V0_3")
    assert "giant-redemption-procedure" in giant[0]["evidenceConcepts"]
    single = rank("单个投资者赎回超过总份额10%的部分如何处理？", [
        candidate(1, 8000, "赎回申请经确认后办理。"),
        candidate(2, 6500, "单个投资者赎回超过总份额10%的部分，管理人有权暂停接受或延缓支付。"),
    ], "STRUCTURE_V0_3")
    assert "single-investor-redemption" in single[0]["evidenceConcepts"]
    complete = rank("零申购费和赎回费是否代表没有其他费用？", [
        candidate(1, 8500, "投资者无需支付申购费，也无需支付赎回费。"),
        candidate(2, 6500, "投资者无需支付申购费，也无需支付赎回费；另有固定投资管理费和托管费。"),
    ], "STRUCTURE_V0_3")
    assert "complete-product-fee-schedule" in complete[0]["evidenceConcepts"]


def test_fee_question_focus_distinguishes_zero_fees_from_rate_schedule():
    zero = _evidence_concepts(
        "申购费和赎回费为0是否代表没有其他费用？",
        "投资者无需支付申购费，投资者无需支付赎回费。")
    assert "zero-fee-question-focus" in zero
    rates = _evidence_concepts(
        "固定管理费、托管费和销售服务费率分别是多少？",
        "固定投资管理费率0.15%，托管费率0.02%，销售服务费率0.30%。")
    assert "explicit-fee-rates" in rates


def test_fee_discount_period_outranks_base_rate_for_discount_question():
    ranked = rank("优惠期间固定管理费优惠后费率是多少？", [
        candidate(1, 8500, "固定投资管理费率为0.15%。"),
        candidate(2, 6500, "阶段性费率优惠：优惠生效日期11月1日，优惠截止日期11月7日，优惠后费率0.05%。"),
    ], "STRUCTURE_V0_3")
    assert "fee-discount-period" in ranked[0]["evidenceConcepts"]


def test_support_policy_treats_explicit_fee_rate_as_fee_evidence():
    supported, _ = support_decision(
        "是否完全不收费？", "固定投资管理费率0.2%，赎回费率为0。",
        "EVIDENCE_SUPPORT_V0_1")
    assert supported is True


def test_business_rank_prefers_product_source_for_product_specific_question():
    values = [
        {**candidate(1, 7000, "我行将理财产品风险分为五级"),
         "sourceIds":["investor-rights"]},
        {**candidate(2, 6500, "本产品风险级别为2：中低风险"),
         "sourceIds":["product-spec"]},
    ]
    ranked = rank("这款产品的风险等级是什么？", values,
                  "STRUCTURE_V0_3")
    assert ranked[0]["sourceIds"] == ["product-spec"]


def test_specific_redemption_intent_demotes_generic_redemption_evidence():
    values = [candidate(1, 9000, "交易日可提出赎回"),
              candidate(2, 7800, "部分赎回后剩余份额不得低于1万份")]
    ranked = rank("部分赎回后剩余9000份怎么处理？", values,
                  "STRUCTURE_V0_3")
    assert "partial-redemption" in ranked[0]["evidenceConcepts"]


def test_live_channel_state_is_not_supported_by_static_product_evidence():
    supported, reason = support_decision(
        "今天手机银行是否可以提交申购？", "说明书提到手机银行渠道",
        "EVIDENCE_SUPPORT_V0_1")
    assert supported is False
    assert "authorized product service" in reason
