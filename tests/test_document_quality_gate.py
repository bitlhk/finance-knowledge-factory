from quality.publication_gate import assess


def inputs():
    structure = {"structureCoverageBps": 10000, "anchorAccuracyBps": 10000,
                 "parserCoverageBps": 10000, "missingArticleNumbers": []}
    mapping = {"coverageBps": 10000}
    retrieval = {"execution":"CORE_EXECUTED",
                 "metricsBps": {"recallAt3": 10000, "hitAt1": 10000, "mrr": 10000,
                                "noAnswerFalsePositive": 0}, "cases": [{"passed": True}]}
    answer = {"execution": "REAL_HARNESS_DEEPSEEK",
              "metricsBps": {"factAccuracy": 10000, "citationAccuracy": 10000},
              "cases": [{"classification": "CORRECT"}]}
    return structure, mapping, retrieval, answer


def test_complete_quality_evidence_passes():
    assert assess(*inputs())["decision"] == "PASS"


def test_each_quality_dimension_fails_closed():
    mutations = [
        lambda values: values[0].update(structureCoverageBps=9999),
        lambda values: values[0].update(anchorAccuracyBps=9999),
        lambda values: values[1].update(coverageBps=9999),
        lambda values: values[2]["metricsBps"].update(recallAt3=9999),
        lambda values: values[2]["metricsBps"].update(noAnswerFalsePositive=1),
        lambda values: values[3].update(execution="NOT_RUN"),
        lambda values: values[3]["metricsBps"].update(citationAccuracy=9999),
    ]
    for mutate in mutations:
        values = list(inputs())
        mutate(values)
        assert assess(*values)["decision"] == "REJECT"
