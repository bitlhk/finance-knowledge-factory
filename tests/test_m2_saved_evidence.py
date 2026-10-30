"""Validate the retained run's hash closure, without replaying any upstream call."""
import hashlib
import json
from pathlib import Path

from knowledge_core.contracts import digest


def test_saved_final_service_run_closure():
    root=Path(__file__).resolve().parents[1]
    report=json.loads((root/'evidence/m2-service-integration/attempt-003.json').read_text())
    assert report['sourceDigest']==hashlib.sha256((root/'tests/fixtures/m2-document.html').read_bytes()).hexdigest()
    assert report['status']=='PASSED_LIMITED_AB_SERVICE_PATH'
    assert report['browser']==report['builder']=='NOT_EXECUTED'
    assert report['manifestDigest']==digest(report['manifest'])
    assert report['objects']['indexDigest']==digest(report['index'])
    assert len(report['validation']['results'])==3
    assert all(r['passed'] for r in report['validation']['results'])
    assert len(report['negativeChecks'])==8
    assert all(r['passed'] for r in report['negativeChecks'])
    assert report['restartReplayEqual'] and report['isolatedApiStopped']
    for receipt in report['receipts']:
        receipt=dict(receipt)
        sha=receipt.pop('receiptDigest')
        assert digest(receipt)==sha
        assert receipt['manifestDigest']==report['manifestDigest']
