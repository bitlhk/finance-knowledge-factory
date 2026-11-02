from knowledge_core.contracts import digest
from knowledge_core.documents import _answer_references, _evaluate_answer_case


def evidence(clause, quote, source_reference=None):
    value = {'coreReceiptDigest':'a' * 64, 'clause':clause, 'quote':quote,
             'quoteDigest':'b' * 64, 'sourceDigest':'c' * 64,
             'originalDigest':'d' * 64, 'chunkId':'chunk'}
    if source_reference:
        value['sourceReference'] = source_reference
    value['evidenceDigest'] = digest(value)
    return value


def runtime_case(answer, retrieved):
    citations, unmatched = _answer_references(answer, retrieved)
    return {'answer':answer, 'retrievedEvidence':retrieved,
            'answerCitations':citations, 'unmatchedAnswerCitations':unmatched}


def gold(expected=None, facts=None, forbidden=None):
    return {'caseId':'case', 'expectedClauses':expected or [],
            'answerFacts':facts or [], 'forbiddenClaims':forbidden or []}


def test_correct_refusal_may_retain_background_evidence():
    retrieved = [evidence('第二条', '第二条 本制度不包含具体产品收益排名。')]
    result = _evaluate_answer_case(
        gold(forbidden=['具体产品收益排名']),
        runtime_case('根据第二条，现有依据不足，无法确认具体产品收益排名。', retrieved))
    assert result['classification'] == 'CORRECT_REFUSAL'
    assert result['retrievedEvidence'] == retrieved
    assert result['citedClauses'] == ['第二条']


def test_wrong_and_fabricated_citations_fail():
    retrieved = [evidence('第一条', '第一条 客户事实从客户服务取得。'),
                 evidence('第二条', '第二条 产品事实从产品服务取得。')]
    wrong = _evaluate_answer_case(
        gold(['第一条'], ['客户事实']),
        runtime_case('根据第二条，客户事实从客户服务取得。', retrieved))
    fabricated = _evaluate_answer_case(
        gold(['第一条'], ['客户事实']),
        runtime_case('根据第九十九条，客户事实从客户服务取得。', retrieved))
    assert wrong['classification'] == 'ANSWER_FACT_ERROR'
    assert fabricated['classification'] == 'ANSWER_FACT_ERROR'
    assert fabricated['unmatchedAnswerCitations'] == ['第九十九条']


def test_original_document_subsection_is_not_a_fabricated_core_citation():
    retrieved = [evidence('第五条', '第五条 余额规则。'),
                 evidence('第七条', '第七条 6.申购、赎回程序：申请由管理人确认。')]
    accepted = _evaluate_answer_case(
        gold(['第五条'], ['余额规则']),
        runtime_case('证据[1]第五条载明余额规则；证据[2]第七条第6条说明确认程序。', retrieved))
    fabricated = runtime_case(
        '证据[1]第五条载明余额规则，并称原文件第99条另有规定。', retrieved)
    assert accepted['classification'] == 'CORRECT'
    assert accepted['unmatchedAnswerCitations'] == []
    assert fabricated['unmatchedAnswerCitations'] == ['第99条']


def test_manager_confirmation_is_semantically_equivalent_to_effectiveness_rule():
    retrieved = [evidence('第七条',
        '管理人在确认日对投资者的赎回申请有效性进行登记确认。')]
    result = _evaluate_answer_case(
        gold(['第七条'], ['申请是否生效以管理人确认为准']),
        runtime_case('依据[1]，赎回申请须经管理人确认有效性后方为成功。', retrieved))
    assert result['classification'] == 'CORRECT'
    reordered = _evaluate_answer_case(
        gold(['第七条'], ['申请是否生效以管理人确认为准']),
        runtime_case('依据[1]，管理人会在确认日对申请有效性进行登记确认。', retrieved))
    assert reordered['classification'] == 'CORRECT'


def test_forbidden_conclusion_is_rejected_but_negated_mention_is_allowed():
    retrieved = [evidence('第一条', '第一条 历史对话摘要不能代替当前客户事实。')]
    forbidden = gold(['第一条'], [], ['历史对话摘要'])
    asserted = _evaluate_answer_case(
        forbidden, runtime_case('根据第一条，历史对话摘要可以代替当前客户事实。', retrieved))
    negated = _evaluate_answer_case(
        forbidden, runtime_case('根据第一条，历史对话摘要不能代替当前客户事实。', retrieved))
    assert asserted['classification'] == 'ANSWER_FACT_ERROR'
    assert asserted['forbiddenClaimChecks'][0]['asserted'] is True
    assert negated['classification'] == 'CORRECT'


def test_semantic_paraphrase_passes_only_with_cited_support():
    retrieved = [evidence('产品说明书/费用',
                          '固定投资管理费按0.2%（年率）收取。')]
    accepted = _evaluate_answer_case(
        gold(['产品说明书/费用'], ['固定投资管理费率0.2%年率']),
        runtime_case('依据[1]，固定管理费的年费率为0.2%。', retrieved))
    unsupported = _evaluate_answer_case(
        gold(['产品说明书/费用'], ['固定投资管理费率0.2%年率']),
        runtime_case('固定管理费的年费率为0.2%。', []))
    assert accepted['classification'] == 'CORRECT'
    assert accepted['factChecks'][0]['method'] == 'DETERMINISTIC_FACT_SUPPORT_V0_3'
    assert unsupported['classification'] == 'ANSWER_FACT_ERROR'


def test_strict_amount_mismatch_remains_rejected():
    retrieved = [evidence('产品说明书/申购',
                          '首次申购起点金额1万元，追加申购为1000元整数倍。')]
    wrong = _evaluate_answer_case(
        gold(['产品说明书/申购'], ['首次申购起点1万元']),
        runtime_case('依据[1]，首次申购起点是1000元。', retrieved))
    assert wrong['classification'] == 'ANSWER_FACT_ERROR'
    assert wrong['factChecks'][0]['missingAnswerValues'] == ['10000元']


def test_negated_prohibition_does_not_become_positive_permission():
    retrieved = [evidence('投资者权益/资金来源',
                          '投资者不得使用贷款等非自有资金投资理财产品。')]
    result = _evaluate_answer_case(
        gold(['投资者权益/资金来源'], ['不得使用贷款等非自有资金投资理财产品'],
             ['贷款资金可以购买']),
        runtime_case('依据[1]，不得使用贷款资金购买。', retrieved))
    assert result['classification'] == 'CORRECT'


def test_risk_level_is_a_strict_value_and_wrong_level_is_rejected():
    retrieved = [evidence('产品说明书/风险', '产品风险级别为2：中低风险。')]
    wrong = _evaluate_answer_case(
        gold(['产品说明书/风险'], ['风险级别为2：中低风险']),
        runtime_case('依据[1]，风险等级为3级。', retrieved))
    assert wrong['classification'] == 'ANSWER_FACT_ERROR'
    assert wrong['factChecks'][0]['missingAnswerValues'] == ['风险等级2级']


def test_risk_level_format_variants_match_the_same_strict_value():
    retrieved = [evidence('产品说明书/风险', '产品风险级别 2：中低风险。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/风险'], ['风险级别为2：中低风险']),
        runtime_case('依据[1]，产品风险等级为2级，属于中低风险。', retrieved))
    assert result['classification'] == 'CORRECT'


def test_live_system_boundary_requires_answer_but_not_document_support():
    retrieved = [evidence('产品说明书/适当性', '适合稳健型及以上投资者。')]
    gold_case = gold(['产品说明书/适当性'], ['需要核实客户当前有效风险评级'])
    accepted = _evaluate_answer_case(
        gold_case, runtime_case('依据[1]，仍需要核实客户当前有效风险评级。', retrieved))
    missing = _evaluate_answer_case(
        gold_case, runtime_case('依据[1]，产品适合稳健型投资者。', retrieved))
    assert accepted['classification'] == 'CORRECT'
    assert accepted['factChecks'][0]['method'] == 'LIVE_SYSTEM_BOUNDARY_V0_1'
    assert missing['classification'] == 'ANSWER_FACT_ERROR'


def test_reordered_forbidden_profit_guarantee_is_rejected():
    retrieved = [evidence('产品说明书/风险', '本产品不保证本金和收益。')]
    gold_case = gold(['产品说明书/风险'], [], ['收益保证'])
    asserted = _evaluate_answer_case(
        gold_case, runtime_case('依据[1]，银行保证收益。', retrieved))
    negated = _evaluate_answer_case(
        gold_case, runtime_case('依据[1]，银行不保证收益。', retrieved))
    assert asserted['classification'] == 'ANSWER_FACT_ERROR'
    assert negated['classification'] == 'CORRECT'


def test_answer_citation_preserves_digest_bound_source_reference():
    reference = {'displayLabel':'产品说明书，第3页'}
    retrieved = [evidence('第一个内部单元', '产品风险级别为2。', reference)]
    citations, unmatched = _answer_references('依据[1]，产品风险级别为2。', retrieved)
    assert not unmatched
    assert citations[0]['sourceReference'] == reference
    assert citations[0]['retrievedEvidenceDigests'] == [retrieved[0]['evidenceDigest']]


def test_business_logic_rejects_right_as_mandatory_action():
    retrieved = [evidence('产品说明书/部分赎回',
                          '余额低于1万份时，管理人有权办理强制全部赎回。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/部分赎回'],
             ['管理人有权将低于1万份的部分赎回申请办理为强制全部赎回']),
        runtime_case('依据[1]，余额低于1万份时，管理人必须强制全部赎回。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'
    assert result['factChecks'][0]['logicalChecks'][0]['check'] == 'RIGHT_NOT_OBLIGATION'


def test_business_logic_accepts_explicit_not_mandatory_scope():
    retrieved = [evidence('产品说明书/部分赎回',
                          '余额低于1万份时，管理人有权办理强制全部赎回。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/部分赎回'],
             ['管理人有权而非必须办理强制全部赎回']),
        runtime_case('依据[1]，管理人有权办理强制全部赎回，但这不是必须操作。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_business_logic_rejects_unqualified_forced_outcome_despite_later_caveat():
    retrieved = [evidence('产品说明书/部分赎回',
                          '余额低于1万份时，管理人有权办理强制全部赎回。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/部分赎回'],
             ['管理人有权将低于1万份的部分赎回申请办理为强制全部赎回']),
        runtime_case('依据[1]，该申请将导致余额被强制赎回；但管理人只是有权，不是必须。',
                     retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_business_logic_accepts_forced_outcome_conditioned_on_exercised_right():
    retrieved = [evidence('产品说明书/部分赎回',
                          '余额低于1万份时，管理人有权办理强制全部赎回。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/部分赎回'],
             ['管理人有权将低于1万份的部分赎回申请办理为强制全部赎回']),
        runtime_case('依据[1]，管理人有权而非必须将低于1万份的部分赎回申请办理为强制全部赎回；如果管理人行使该权利，将导致余额被强制赎回。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_business_logic_accepts_not_certain_without_treating_it_as_duty():
    retrieved = [evidence('产品说明书/大额赎回',
                          '管理人有权暂停接受当日申请，下一交易日继续接受。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/大额赎回'],
             ['管理人有权暂停当日申请，下一交易日继续接受']),
        runtime_case('依据[1]，申请不一定在当天受理；管理人有权暂停，下一交易日继续接受。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_business_logic_rejects_same_day_for_t_plus_one():
    retrieved = [evidence('产品说明书/赎回',
                          'T日赎回，本金和收益T+1日到账。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/赎回'], ['T日赎回，本金和收益T+1日到账']),
        runtime_case('依据[1]，T日赎回后本金和收益当日到账。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'
    assert 'BUSINESS_LOGIC_CONTRADICTION' in result['factChecks'][0]['reasons']


def test_business_logic_requires_termination_and_redemption_distinction():
    retrieved = [evidence('产品说明书/终止', '理财客户无提前终止权。'),
                 evidence('产品说明书/赎回', '每个交易日开放申购和赎回。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/终止', '产品说明书/赎回'],
             ['客户无权提前终止整个产品与正常赎回不是同一概念']),
        runtime_case('依据[1][2]，客户不能提前终止整个产品。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_business_logic_limits_zero_rate_to_subscription_and_redemption_fees():
    retrieved = [evidence('产品说明书/费率',
                          '申购和赎回的费率均为0，另有管理费和托管费。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/费率'], ['申购和赎回费率均为0']),
        runtime_case('依据[1]，这款产品完全没有任何费用。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_business_logic_accepts_zero_fees_with_other_charges_preserved():
    retrieved = [evidence('产品说明书/费率',
                          '申购和赎回的费率均为0，另有管理费、托管费和税费。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/费率'], ['申购和赎回费率均为0']),
        runtime_case('依据[1]，申购和赎回费率均为0，但仍有管理费、托管费和税费。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_business_logic_rejects_historical_yield_as_current():
    retrieved = [evidence('产品说明书/收益', '过往业绩不代表未来表现。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/收益'], ['过往业绩不代表当前收益率']),
        runtime_case('依据[1]，过往业绩表明今天的收益率是1.2%。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_product_rule_does_not_prove_completed_customer_suitability():
    retrieved = [evidence('产品说明书/适当性', '本产品适合稳健型投资者。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/适当性'], ['产品适合投资者包括稳健型']),
        runtime_case('依据[1]，该客户已完成适当性审核。', retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_negated_customer_suitability_claim_is_not_a_false_positive():
    retrieved = [evidence('产品说明书/适当性', '本产品适合稳健型投资者。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/适当性'], ['产品适合投资者包括稳健型']),
        runtime_case('依据[1]，产品适合投资者包括稳健型；该规则不能证明客户已通过购买审核，仍需实时核实。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_long_negated_customer_suitability_claim_is_not_a_false_positive():
    retrieved = [evidence('产品说明书/适当性', '本产品适合稳健型投资者。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/适当性'], ['产品适合投资者包括稳健型']),
        runtime_case('依据[1]，产品适合投资者包括稳健型；文件并未载明某位客户的实际评级或已通过购买审核。',
                     retrieved))
    assert result['classification'] == 'CORRECT'


def test_contrast_resets_negated_customer_suitability_scope():
    retrieved = [evidence('产品说明书/适当性', '本产品适合稳健型投资者。')]
    result = _evaluate_answer_case(
        gold(['产品说明书/适当性'], ['产品适合投资者包括稳健型']),
        runtime_case('依据[1]，文件未说明个人评级，但该客户已通过购买审核。',
                     retrieved))
    assert result['classification'] == 'ANSWER_FACT_ERROR'


def test_calendar_boundary_rejects_unverified_certain_weekday():
    retrieved = [evidence('产品说明书/到账',
                          'T日赎回后T+1日到账，遇节假日顺延。')]
    gold_case = gold(['产品说明书/到账'],
                     ['需要核实实际交易日历，不得推断确定到账日期'])
    wrong = _evaluate_answer_case(
        gold_case,
        runtime_case('依据[1]，资金确定下周一到账。', retrieved))
    accepted = _evaluate_answer_case(
        gold_case,
        runtime_case('依据[1]，需要核实实际交易日历，不能确定下周一到账。',
                     retrieved))
    assert wrong['classification'] == 'ANSWER_FACT_ERROR'
    assert accepted['classification'] == 'CORRECT'
