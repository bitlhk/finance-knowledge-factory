import pytest

from probes.wiki.worker_probe import SOURCE, anchors, source_text, assess_page
from probes.wiki.handoff import assess


def page():
    return "---\ntitle: test\n---\n## 原文出处\n" + "\n".join(f"[[source:S{i}]]" for i in range(1, 5))


def test_valid_anchors_still_require_semantic_review():
    result = assess_page(page(), SOURCE, "stop")
    assert result["structuralPassed"]
    assert result["semanticQuality"] == "REVIEW_REQUIRED"
    assert not result["publicationAllowed"]


@pytest.mark.parametrize("finish", ["length", None, "error"])
def test_truncated_generation_not_accepted(finish):
    assert not assess_page(page(), SOURCE, finish)["structuralPassed"]


def test_partial_coverage_not_success():
    assert "PARTIAL_SOURCE_COVERAGE" in assess_page(page().replace("[[source:S4]]", ""), SOURCE, "stop")["errors"]


def test_unknown_anchor_rejected():
    assert "UNKNOWN_ANCHOR" in assess_page(page() + "[[source:S5]]", SOURCE, "stop")["errors"]


def test_no_silent_source_truncation():
    with pytest.raises(ValueError, match="BUDGET"):
        source_text({"lines": ["x" * 12001]})


def test_line_anchors_use_real_text_lines():
    result = anchors(SOURCE)
    assert [a["quote"] for a in result] == SOURCE["lines"]
    assert [a["lineStart"] for a in result] == [1, 2, 3, 4]
    assert all("page" not in a for a in result)


def test_unresolved_raw_link_not_invented_as_file():
    result = assess(page() + "[[raw/nonexistent]]", [])
    assert result["candidateAdmission"] == "BLOCKED"
    assert result["unresolvedPages"] == ["raw/nonexistent"]


def test_unbalanced_fence_rejected():
    assert "UNBALANCED_CODE_FENCE" in assess(page() + "\n```", [])["errors"]


def test_traceable_pages_do_not_imply_semantic_pass():
    result = assess(page() + "[[raw/known]]", ["raw/known"])
    assert result["candidateAdmission"] == "REVIEW_REQUIRED"
