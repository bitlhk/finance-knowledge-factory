"""Candidate profiles and deterministic structural ranking for experiments."""
from m2.ragflow import BASELINE_RETRIEVAL
from knowledge_core.retrieval_quality import (merge_candidates, query_variants,
                                              rank, support_decision)


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
    "financial-document-v02": {"retrieval": {**BASELINE_RETRIEVAL, "pageSize": 12,
                                                "keywordWeightBps": 5000},
                               "postRank": "STRUCTURE_V0_2", "selectionThresholdBps": 3300,
                               "queryPlanner": "DETERMINISTIC_FINANCIAL_V0_1",
                               "supportPolicy": "EVIDENCE_SUPPORT_V0_1"},
}
