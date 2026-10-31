import hashlib
import json
from pathlib import Path

from knowledge_core.contracts import digest

ROOT=Path(__file__).resolve().parents[1]/'evidence/m2-web'


def test_saved_ui_evidence_hashes_and_core_publication_closure():
    index=json.loads((ROOT/'INDEX.json').read_text())
    for name,sha in index['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha
    objects=json.loads((ROOT/'core-objects.json').read_text())
    assert all(digest(o['body'])==sha for sha,o in objects.items())
    manifest=objects[index['manifestDigest']]['body']
    for field in ['candidateDigest','validationDigest','approvalDigest','indexDigest','sourceDigest']:
        assert manifest[field] in objects
    approval=objects[manifest['approvalDigest']]['body']
    assert approval['candidateDigest']==manifest['candidateDigest']
    assert approval['validationDigest']==manifest['validationDigest']
    assert approval['decision']=='ISOLATED_TEST_APPROVAL'
    result=json.loads((ROOT/'browser-r2/result.json').read_text())
    assert result['status']=='PASSED' and result['run']['id']==index['runId']
    assert len(result['run']['artifact']['validation']['retrievalTests'])==3
    assert all(t['passed'] for t in result['run']['artifact']['validation']['retrievalTests'])
    assert result['query']['receipt']['manifestDigest']==index['manifestDigest']
    assert index['harnessInstallation']=='NOT_COMPLETED'


def test_saved_native_outage_and_recovery_are_not_mock_success():
    result=json.loads((ROOT/'browser-outage-r3/result.json').read_text())
    assert result['status']=='PASSED'
    assert [r['status'] for r in result['posts']]==[200,409,200]
    assert result['posts'][1]['body']=={'error':'RAGFLOW_UNAVAILABLE'}
    assert result['replayIssuedNoSearch'] and result['recovered']
    assert result['errors']==[]
