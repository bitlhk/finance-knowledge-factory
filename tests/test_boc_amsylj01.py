import copy
import json
from pathlib import Path

import pytest

from business_knowledge import boc_amsylj01 as product
from knowledge_core.contracts import Rejected, digest
from knowledge_core.document_quality import validate_test_set
from knowledge_core.documents import DocumentCore
from m2.web import DocumentProduction
from tests.test_document_quality_publication import AUTHOR, QualityClient
from tools.build_amsylj01_quality_set_v02 import build as build_quality_set_v02


ROOT = Path(__file__).parents[1] / "examples/business/customer-manager/amsylj01"
SOURCES = ROOT / "sources"
GENERATED = ROOT / "generated"
BUSINESS = ROOT.parent / "boc-wealth-manager-test-set-v0.1.json"


def committed_pages():
    return json.loads((GENERATED / "amsylj01-pdf-pages.json").read_text(encoding="utf-8"))


def test_official_source_bytes_and_committed_bundle_are_reproducible(monkeypatch):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    bundle = product.build_bundle(SOURCES)
    assert bundle["html"] == (GENERATED / "amsylj01-derived.html").read_bytes()
    assert bundle["provenance"] == json.loads(
        (GENERATED / "amsylj01-provenance.json").read_text(encoding="utf-8"))
    assert len(bundle["chunks"]) == 24
    assert {item["sourceId"] for mapping in bundle["provenance"]["mappings"]
            for item in mapping["originalAnchors"]} == {
                "product-spec", "sales-agreement", "investor-rights"}
    assert all(mapping["originalAnchors"] for mapping in
               bundle["provenance"]["mappings"])


def test_source_digest_page_or_anchor_damage_fails_closed(monkeypatch, tmp_path):
    copied = tmp_path / "sources"
    copied.mkdir()
    for filename in product.SOURCE_FILES.values():
        (copied / filename).write_bytes((SOURCES / filename).read_bytes())
    (copied / "sales-agreement.html").write_bytes(
        (copied / "sales-agreement.html").read_bytes() + b"\n")
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_DIGEST_MISMATCH"):
        product.build_bundle(copied)

    pages = committed_pages()
    pages[0] = pages[0].replace("风险级别", "风险分类", 1)
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:pages)
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_MARKER"):
        product.build_bundle(SOURCES)


def test_compiled_18_case_contract_preserves_business_gold(monkeypatch):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    bundle = product.build_bundle(SOURCES)
    business = json.loads(BUSINESS.read_text(encoding="utf-8"))
    quality = product.compile_quality_set(
        business, digest(bundle["source"]), bundle["provenance"])
    validate_test_set(quality, {item["clause"] for item in bundle["chunks"]})
    assert len(quality["cases"]) == 18
    assert quality == json.loads((GENERATED /
        "amsylj01-core-quality-set-v0.1.json").read_text(encoding="utf-8"))
    original = {item["caseId"]:item for item in business["cases"]}
    compiled = {item["caseId"]:item for item in quality["cases"]}
    aliases = {item["clause"]:item["coreClause"]
               for item in bundle["provenance"]["mappings"]}
    for case_id, item in original.items():
        assert compiled[case_id]["question"] == item["question"]
        assert compiled[case_id]["expectedClauses"] == [
            aliases[value] for value in item["requiredEvidence"]]
        assert compiled[case_id]["forbiddenClaims"] == item["forbiddenClaims"]


def test_provenance_digest_is_immutable(monkeypatch):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    bundle = product.build_bundle(SOURCES)
    damaged = copy.deepcopy(bundle["provenance"])
    damaged["mappings"][0]["originalAnchors"][0]["page"] = 2
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_PROVENANCE_MISMATCH"):
        product.verify_bundle(SOURCES, bundle["html"], damaged)


def test_verified_bundle_enters_normal_candidate_and_quality_contract(monkeypatch,
                                                                      tmp_path):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    bundle = product.build_bundle(SOURCES)
    business = json.loads(BUSINESS.read_text(encoding="utf-8"))
    core = DocumentCore(tmp_path / "core.db")
    try:
        grants = []
        for principal in (AUTHOR.principal, "reader"):
            grants += [
                {"principal":principal, "resource":"product:" + product.PRODUCT_ID,
                 "actions":["consume", "history"]},
                {"principal":principal,
                 "resource":"source:" + product.PRODUCT_ID + "-source",
                 "actions":["source_read"]},
            ]
        core.set_policy(AUTHOR, {"schemaVersion":"active-policy.v0.1",
            "revision":1, "grants":grants}, 0)
        result = product.produce_candidate(core, AUTHOR, bundle, {
            "regions":["CN-BJ"], "institutions":["boc"],
            "products":["AMSYLJ01"],
            "purposes":["customer-manager-service-preparation"],
            "validFrom":"2025-02-28", "validTo":None,
            "timezone":"Asia/Shanghai"}, business, ["reader"], QualityClient())
        test_set = core.register_quality_test_set(
            AUTHOR, result["candidateDigest"], result["qualityTestSet"], 1)
        assert core._get(AUTHOR, test_set, "document-quality-test-set")[
            "testSet"]["cases"] == result["qualityTestSet"]["cases"]
        assert result["provenanceDigest"] == bundle["provenance"][
            "provenanceDigest"]
    finally:
        core.close()


def test_workbench_loads_fixed_business_sample_without_enabling_model(monkeypatch,
                                                                      tmp_path):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    client = QualityClient()
    service = DocumentProduction(tmp_path, lambda:client)
    try:
        loaded = service.business_sample("boc-amsylj01")
        source = loaded["source"]
        assert source["businessProduct"]["sourceCount"] == 3
        assert source["businessProduct"]["qualityCaseCount"] == 18
        assert source["businessProduct"]["provenanceDigest"] == json.loads(
            (GENERATED / "amsylj01-provenance.json").read_text())["provenanceDigest"]
        assert len(loaded["tests"]) == 16
        assert service.snapshot()["modelReady"] is False
    finally:
        service.close()


def test_source_references_use_official_locations_not_synthetic_article_numbers(monkeypatch):
    monkeypatch.setattr(product, "_pdf_pages", lambda unused:committed_pages())
    bundle = product.build_bundle(SOURCES)
    references = product.source_references(bundle["provenance"])
    assert len(references) == 24
    risk = next(item for item in references if item["clause"] == "第一条")
    assert "PDF第1页" in risk["displayLabel"]
    assert "产品说明书及风险揭示书" in risk["documentTitle"]
    assert "第一条" not in risk["displayLabel"]
    agreement = next(item for item in references
                     if item["clause"] == "第十八条")
    assert agreement["locators"][0]["locatorKind"] == "HTML_DOM_NORMALIZED_TEXT"


def test_v02_quality_set_preserves_v01_and_separates_platform_authority():
    original = json.loads(BUSINESS.read_text(encoding="utf-8"))
    snapshot = copy.deepcopy(original)
    blind = json.loads((ROOT / "analysis/blind-business-cases-v0.1.json")
                       .read_text(encoding="utf-8"))
    improved = build_quality_set_v02(original, blind)
    assert original == snapshot
    assert len(improved["cases"]) == 21
    assert "wm-018-version-change" not in {item["caseId"] for item in improved["cases"]}
    assert {item["caseId"] for item in improved["goldChanges"]} == {
        "wm-001-risk-level", "wm-002-c1-suitability",
        "wm-006-minimum-subscription", "wm-008-fees",
        "wm-009-principal-guarantee", "wm-010-non-own-funds"}
