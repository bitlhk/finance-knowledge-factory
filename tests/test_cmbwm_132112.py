import base64
import copy
import hashlib
from pathlib import Path

import pytest

from business_knowledge import cmbwm_132112 as product
from knowledge_core.contracts import Rejected
from m2.web import DocumentProduction
from tests.test_document_quality_publication import QualityClient


ROOT = Path(__file__).parents[1] / "examples/business/customer-manager/cmbwm-132112/sources"


def values():
    return {key:(ROOT / metadata["filename"]).read_bytes()
            for key,metadata in product.SOURCES.items()}


def upload_body(source_values=None):
    source_values = source_values or values()
    return {"registrationId":product.REGISTRATION_ID, "files":[{
        "sourceId":key, "filename":metadata["filename"],
        "contentBase64":base64.b64encode(source_values[key]).decode("ascii")}
        for key,metadata in product.SOURCES.items()]}


def test_official_upload_bundle_has_fixed_bytes_pages_and_business_cases():
    bundle = product.build_bundle(values())
    assert len(bundle["chunks"]) == 13
    assert len(bundle["tests"]) == 15
    assert {item["clause"] for item in bundle["sourceReferences"]} == {
        item["clause"] for item in bundle["chunks"]}
    assert {locator["sourceId"] for item in bundle["sourceReferences"]
            for locator in item["locators"]} == set(product.SOURCES)
    assert next(item for item in bundle["sourceReferences"]
                if item["clause"] == "第九条")["locators"][1]["page"] == 44
    for key,metadata in product.SOURCES.items():
        assert hashlib.sha256(values()[key]).hexdigest() == metadata["sha256"]


def test_upload_rejects_missing_changed_or_renamed_official_file():
    body = upload_body()
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_SET_INCOMPLETE"):
        product.decode_uploads(body["files"][:-1])
    changed = copy.deepcopy(body)
    changed["files"][0]["contentBase64"] = base64.b64encode(b"%PDF-damaged").decode()
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_DIGEST_MISMATCH"):
        product.decode_uploads(changed["files"])
    renamed = copy.deepcopy(body)
    renamed["files"][0]["filename"] = "different.pdf"
    with pytest.raises(Rejected, match="BUSINESS_SOURCE_UPLOAD_INVALID"):
        product.decode_uploads(renamed["files"])


def test_workbench_import_preserves_original_files_and_source_references(tmp_path):
    service = DocumentProduction(tmp_path, lambda:QualityClient())
    try:
        loaded = service.import_business_product(upload_body())
        source = loaded["source"]
        assert source["businessProduct"]["productCode"] == "132112"
        assert source["businessProduct"]["currentSaleStatus"] == "REQUIRES_LIVE_PRODUCT_SYSTEM"
        assert len(source["businessProduct"]["sourceReferences"]) == 13
        assert len(loaded["tests"]) == 15
        stored = tmp_path / "imports" / source["id"]
        for key,metadata in product.SOURCES.items():
            path = stored / metadata["filename"]
            assert path.read_bytes() == values()[key]
            assert path.stat().st_mode & 0o777 == 0o600
    finally:
        service.close()


def test_normal_candidate_index_uses_original_pdf_page_references(tmp_path):
    client = QualityClient()
    client.operations = []
    service = DocumentProduction(tmp_path, lambda:client)
    try:
        loaded = service.import_business_product(upload_body())
        job = service.submit({"requestId":"cmbwm-normal-build", "sourceId":loaded["source"]["id"],
            "rules":False, "clauses":[], "tests":loaded["tests"], "modelConsent":False})
        service.pool.shutdown(wait=True)
        completed = service.get(job["id"])
        # The deterministic test client always retrieves its first chunk; this
        # test verifies provenance plumbing, not retrieval quality admission.
        assert completed["status"] == "PARTIAL"
        core = service.core()
        try:
            index = core._get(service.producer, completed["coreObjects"]["indexDigest"],
                              "document-index")
            assert index["schemaVersion"] == "document-index.v0.2"
            assert next(item for item in index["sourceReferences"]
                        if item["clause"] == "第十二条")["locators"][0]["sourceId"] == "fee-discount"
        finally:
            core.close()
    finally:
        service.close()
