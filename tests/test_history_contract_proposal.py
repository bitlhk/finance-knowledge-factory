"""Proposal shape checks only; no history HTTP implementation or acceptance."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from m2.runtime_protocol import SCHEMA as QUERY_SCHEMA
from tests.test_harness_runtime import ready, TOKEN
from m2.acceptance import READER

SCHEMA = json.loads((Path(__file__).resolve().parents[1] /
    'contracts/runtime/knowledge-history-v0.1.proposed.schema.json').read_text())


def validator(kind):
    root = {**SCHEMA, '$ref':'#/$defs/'+kind}
    return Draft202012Validator(root)


def test_bundled_query_definitions_have_only_reference_prefix_changes():
    def normalize(value):
        if isinstance(value,list): return [normalize(v) for v in value]
        if not isinstance(value,dict): return value
        return {k:v.replace('#/$defs/query_','#/$defs/') if k=='$ref' else normalize(v)
            for k,v in value.items()}
    for key,value in SCHEMA['$defs'].items():
        if key.startswith('query_'):
            assert normalize(value)==QUERY_SCHEMA['$defs'][key[len('query_'):]]


def sample():
    return {'schemaVersion':'knowledge-history.v0.1','requestId':'history-read-1','traceId':'history-trace-1',
        'coreReceiptDigest':'a'*64, 'expected':{'productId':'product-1','manifest':'b'*64,
            'sourceDigest':'c'*64,'sourceRevision':1,'originalRequestId':'original-request',
            'originalTraceId':'original-trace'}}


def test_proposal_schema_is_valid_and_request_carries_no_authority():
    Draft202012Validator.check_schema(SCHEMA)
    validator('request').validate(sample())


@pytest.mark.parametrize('field', ['principalId','tenant','actor','roles','permissions','sessionRef','businessDate'])
def test_proposal_rejects_body_authority(field):
    assert not validator('request').is_valid({**sample(),field:'untrusted'})


@pytest.mark.parametrize('change', ['bad-digest','missing-original-trace','wrong-version','boolean-revision'])
def test_proposal_rejects_bad_references(change):
    value=sample()
    if change=='bad-digest': value['coreReceiptDigest']='kr-'+'a'*64
    elif change=='missing-original-trace': value['expected'].pop('originalTraceId')
    elif change=='wrong-version': value['schemaVersion']='knowledge-query.v0.1'
    else: value['expected']['sourceRevision']=True
    assert not validator('request').is_valid(value)


def test_proposed_response_wraps_existing_saved_data_without_reexecuting(ready):
    runtime,body,_,service,client=ready
    original=runtime.query(TOKEN,body)
    core=service.core()
    before=client.calls
    try:
        sha=original['receipt']['coreReceiptDigest']
        replay=core.replay_document(READER,sha)
        saved={k:v for k,v in replay.items() if k not in ('receiptDigest','replay')}
        proposed={'schemaVersion':'knowledge-history.v0.1','code':0,'replay':True,
            'requestId':'history-read-1','traceId':'history-trace-1','coreReceiptDigest':sha,
            'savedReceipt':saved,'queryResponse':original}
        validator('response').validate(proposed)
        assert proposed['requestId'] != proposed['queryResponse']['receipt']['requestId']
        assert proposed['savedReceipt']['requestId']==body['requestId']
        assert client.calls==before
    finally:
        core.close()


def test_proposed_history_type_does_not_accept_run_authority():
    value={'schemaVersion':'knowledge-history-authority.v0.1','enabled':True,'ownerRef':'owner',
        'principalId':'reader','tenant':'test','authority':'trusted-host',
        'purpose':'knowledge.history.read','productId':'product','manifest':'a'*64,
        'allowedReceiptDigests':['b'*64],'expiresAt':'2026-11-01T01:00:00Z','leaseDirectory':'/private/test'}
    validator('hostAuthority').validate(value)
    assert not validator('hostAuthority').is_valid({**value,'schemaVersion':'knowledge-host-authority.v0.1'})
    assert not validator('hostAuthority').is_valid({**value,'purpose':'evidence-query'})
    lease={'schemaVersion':'knowledge-history-lease.v0.1','policyDigest':'a'*64,'ownerRef':'owner',
        'viewerSessionRef':'independent-view','expiresAt':'2026-11-01T01:00:00Z'}
    validator('hostLease').validate(lease)
    assert not validator('hostLease').is_valid({**lease,'schemaVersion':'knowledge-host-lease.v0.1'})
