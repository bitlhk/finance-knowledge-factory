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
    assert accepted['factChecks'][0]['method'] == 'DETERMINISTIC_FACT_SUPPORT_V0_2'
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
