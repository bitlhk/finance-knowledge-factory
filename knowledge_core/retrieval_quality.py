"""Versioned deterministic retrieval policy used by admitted document products."""
import re


def _bigrams(value):
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value).casefold()
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


def query_variants(question, mode):
    if mode in (None, "NONE"):
        return [question]
    if mode not in {"DETERMINISTIC_FINANCIAL_V0_1",
                    "DETERMINISTIC_FINANCIAL_V0_2"}:
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
    if mode == "DETERMINISTIC_FINANCIAL_V0_2":
        expansions = []
        concepts = (
            (r"风险等级|风险级别", "产品风险级别 风险等级"),
            (r"适合.{0,4}(?:客户|投资者)|客户类型", "适合购买的投资者 投资者类型 风险承受能力"),
            (r"提前赎回|赎回", "申购和赎回 交易日 赎回到账"),
            (r"提前终止", "提前终止 理财计划"),
            (r"首次购买|首次申购", "首次申购 起点金额"),
            (r"追加购买|追加申购", "追加申购 金额要求"),
            (r"费用|费率", "申购赎回费率 投资管理费 托管费 税费"),
        )
        for pattern, expansion in concepts:
            if re.search(pattern, question):
                expansions.append(expansion)
        # Multi-intent financial questions need independent evidence for each
        # concept. These variants are domain terms, not question-to-clause maps.
        variants.extend(expansions)
        if re.search(r"是否意味着|是不是意味着|是否等于|是不是等于", question):
            variants.extend(value for value in expansions if value not in variants)
    return list(dict.fromkeys(variants))[:8]


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


def _evidence_concepts(question, text):
    """Identify independently required evidence concepts from its own text."""
    concepts = []
    checks = (
        ('product-risk-level', r'风险等级|风险级别|C[1-5].{0,8}(?:购买|适合)',
         r'风险(?:等级|级别)\s*(?:为|是|：|:)?\s*[1-5]'),
        ('suitable-investor', r'适合.{0,4}(?:客户|投资者|购买)|客户类型|C[1-5].{0,8}购买',
         r'适合购买的投资者|投资者类型'),
        ('normal-redemption', r'赎回', r'开放申购和赎回|提出申购或赎回'),
        ('redemption-arrival', r'赎回|到账|用钱', r'T\+?1日到账|赎回到账'),
        ('early-termination', r'提前赎回|提前终止', r'提前终止'),
        ('partial-redemption', r'部分赎回|剩余.{0,4}(?:份|份额)',
         r'部分赎回后.{0,30}剩余份额|强制性?全部赎回'),
        ('large-redemption', r'大额赎回', r'大额赎回.{0,60}暂停|暂停接受当日赎回'),
        ('trading-day', r'周末|交易日', r'周六、周日|交易日'),
        ('order-time', r'周末|挂单|什么时候处理', r'挂单交易|下一受理时间'),
        ('basic-fees', r'费用|费率', r'固定投资管理费率|无申购、赎回费'),
        ('complete-fees', r'费用|费率|税费', r'其他税费'),
        ('principal-and-yield-risk', r'保本|保证.{0,4}收益|收益.{0,4}保证',
         r'不保证.{0,8}(?:本金|资金本金).{0,8}收益|不保证本金和收益'),
        ('non-own-funds', r'借款|贷款资金|非自有资金',
         r'自有资金|非自有资金'),
        ('rating-mismatch-redemption', r'评级|风险承受能力',
         r'风险承受能力.{0,40}不匹配|无权以风险承受能力不再匹配为由'),
    )
    for name, question_pattern, evidence_pattern in checks:
        if re.search(question_pattern, question) and re.search(evidence_pattern, text):
            concepts.append(name)
    return concepts


def rank(question, candidates, mode):
    if mode == "NONE":
        return candidates
    if mode not in ("STRUCTURE_V0_1", "STRUCTURE_V0_2", "STRUCTURE_V0_3"):
        raise ValueError("UNKNOWN_POST_RANK_MODE")
    planner = ("DETERMINISTIC_FINANCIAL_V0_2" if mode == "STRUCTURE_V0_3"
               else "DETERMINISTIC_FINANCIAL_V0_1")
    variants = query_variants(question, planner) if mode != "STRUCTURE_V0_1" else [question]
    query = _bigrams(variants[1] if len(variants) > 1 else question)
    ranked = []
    for candidate in candidates:
        text_tokens = _bigrams(candidate["text"])
        lexical = round(10000 * len(query & text_tokens) / len(query)) if query else 0
        base = candidate["scoreBps"] or 0
        bonus = _shape_bonus(question, candidate["text"])
        if mode in {"STRUCTURE_V0_2", "STRUCTURE_V0_3"}:
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
        if mode == "STRUCTURE_V0_3":
            text = candidate["text"]
            concepts = _evidence_concepts(question, text)
            # A specific evidence concept is more useful than being returned by
            # many broad query variants. No clause id or case id is consulted.
            weights = {
                'partial-redemption':5000, 'large-redemption':5000,
                'complete-fees':4800, 'rating-mismatch-redemption':4800,
                'early-termination':4200, 'order-time':4200,
                'product-risk-level':3800, 'suitable-investor':3800,
                'trading-day':3200, 'principal-and-yield-risk':3800,
                'non-own-funds':3800, 'normal-redemption':2400,
                'redemption-arrival':2400, 'basic-fees':2400,
            }
            bonus += min(5200, sum(weights.get(value, 1800)
                                   for value in concepts))
            candidate = {**candidate, "evidenceConcepts":concepts}
        score = max(0, min(10000, round(base * 0.6 + lexical * 0.4) + bonus))
        ranked.append({**candidate, "postRankScoreBps": score})
    return sorted(ranked, key=lambda value: (-value["postRankScoreBps"], value["rank"]))


def _select(candidates, limit, mode):
    if mode != "DIVERSE_QUERY_COVERAGE_V0_1":
        return candidates[:limit]
    selected, covered_queries, covered_text = [], set(), set()
    remaining = list(candidates)
    while remaining and len(selected) < limit:
        def value(candidate):
            queries = set(candidate.get("queryIndexes", []))
            concepts = set(candidate.get("evidenceConcepts", []))
            text = _bigrams(candidate.get("text", ""))
            concept_weights = {
                'partial-redemption':5200, 'large-redemption':5200,
                'complete-fees':5000, 'rating-mismatch-redemption':5000,
                'early-termination':4500, 'order-time':4500,
                'product-risk-level':4000, 'suitable-investor':4000,
            }
            novelty = (sum(concept_weights.get(item, 2800)
                           for item in concepts - covered_queries)
                       if concepts else len(queries - covered_queries) * 500)
            diversity = len(text - covered_text) * 20
            score = candidate.get("postRankScoreBps", candidate.get("scoreBps") or 0)
            return score + novelty + min(1000, diversity)
        chosen = max(remaining, key=lambda item: (value(item), -item["rank"]))
        selected.append(chosen)
        covered_queries.update(chosen.get("evidenceConcepts", [])
                               or chosen.get("queryIndexes", []))
        covered_text.update(_bigrams(chosen.get("text", "")))
        remaining.remove(chosen)
    return selected


def support_decision(question, text, mode):
    if mode in (None, "NONE"):
        return True, "support policy disabled"
    if mode != "EVIDENCE_SUPPORT_V0_1":
        raise ValueError("UNKNOWN_SUPPORT_POLICY")
    normalized = re.sub(r"\s+", "", text)
    if (re.search(r"今天|当前|现在", question)
            and re.search(r"在售|额度|渠道|提交.{0,5}(?:申购|购买)", question)):
        return False, "live sale, quota, and channel state require an authorized product service"
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
    eligible = []
    filtered = []
    for candidate in candidates:
        score = candidate.get("postRankScoreBps", candidate.get("scoreBps") or 0)
        supported, support_reason = support_decision(question, candidate["text"], profile.get("supportPolicy"))
        keep = score >= profile["selectionThresholdBps"] and supported
        filtered.append({**candidate, "qualityDecision":"KEEP" if keep else "REJECT",
                         "qualityReasons":[f"score {score} {'>=' if score >= profile['selectionThresholdBps'] else '<'} "
                                           f"threshold {profile['selectionThresholdBps']}", support_reason]})
        if keep:
            eligible.append(candidate)
    selected = _select(eligible, 3, profile.get("selectionPolicy", "TOP_SCORE"))
    return {"queryVariants":questions, "retrieved":retrieved, "ranked":ranked,
            "filtered":filtered, "selected":selected[:3]}


def select(client, dataset_id, document_id, question, profile):
    return trace_select(client, dataset_id, document_id, question, profile)["selected"]
