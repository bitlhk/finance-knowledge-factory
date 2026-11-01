from knowledge_core.contracts import digest
from knowledge_core.documents import _answer_references, _evaluate_answer_case


def evidence(clause, quote):
    value = {'coreReceiptDigest':'a' * 64, 'clause':clause, 'quote':quote,
             'quoteDigest':'b' * 64, 'sourceDigest':'c' * 64,
             'originalDigest':'d' * 64, 'chunkId':'chunk'}
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
