from probes.documents.review_retrieval import match_chunks


def test_cross_reference_is_not_clause_content():
    clauses = [{'clause': '第三十六条', 'text': '第三十六条 支付另有规定。'}]
    assert match_chunks('第三十三条 除第三十六条规定外受托支付。', clauses) == []
    assert match_chunks('第三十六条\n支付另有规定。', clauses) == clauses


def test_truncated_body_is_not_complete_evidence():
    clauses = [{'clause': '第八条', 'text': '第八条 一般五年，例外十年。'}]
    assert match_chunks('第八条 一般五年。', clauses) == []
