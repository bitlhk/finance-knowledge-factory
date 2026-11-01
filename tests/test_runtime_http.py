"""Real loopback HTTP with controlled faults, not real Harness authorization."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading
from urllib import request

import pytest

from m2.synthetic_context import AUTHOR, READER
from m2.harness_runtime import handler
from m2.ragflow import Ragflow, NoRedirect
from tests.runtime_support import http
from m2.runtime_protocol import validate_wire
from m2.runtime_service import IsolatedServer, record
from tests.test_harness_runtime import ready, TOKEN
from tests.test_host_leases import issued


@contextmanager
def listening(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.02})
    thread.start()
    try:
        yield 'http://127.0.0.1:'+str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize('fault,expected', [
    ('business-403','RAGFLOW_BUSINESS_ERROR'),
    ('http-503','RAGFLOW_UNAVAILABLE'),
    ('malformed-json','RAGFLOW_UNAVAILABLE'),
    ('wrong-dataset','RAGFLOW_DATASET_MISMATCH'),
    ('wrong-document','RETRIEVAL_INDEX_MISMATCH'),
    ('changed-text','RETRIEVAL_INDEX_MISMATCH'),
])
def test_http_upstream_failure_and_recovery(ready, fault, expected, record_property):
    runtime, body, _, _, client = ready
    state = {'fault':fault,'calls':0}
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path == '/retrieval'
            state['calls'] += 1
            rows = client.retrieve(payload['dataset_ids'][0],payload['document_ids'][0],payload['question'])
            chunks = [{'id':r['id'],'content':r['text'],'document_id':r['documentId'],
                       'dataset_id':payload['dataset_ids'][0]} for r in rows]
            current = state['fault']
            if current == 'wrong-dataset': chunks[0]['dataset_id'] = 'other'
            if current == 'wrong-document': chunks[0]['document_id'] = 'other'
            if current == 'changed-text': chunks[0]['content'] += 'untrusted-insertion'
            raw = json.dumps({'code':403 if current=='business-403' else 0,'data':{'chunks':chunks}}).encode()
            if current == 'malformed-json': raw = b'not-json'
            self.send_response(503 if current=='http-503' else 200)
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    upstream = ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    with listening(upstream) as upstream_base:
        # Test-only transport injection; production endpoint allow-list is unchanged.
        transport = object.__new__(Ragflow)
        transport.base, transport.token = upstream_base, None
        transport.opener = request.build_opener(NoRedirect())
        runtime.client_factory = lambda:transport
        with listening(IsolatedServer(('127.0.0.1',0),handler(runtime))) as base:
            status, denied = http(base,'/query',TOKEN,body)
            assert status == 403 and denied == {'code':403,'error':expected}
            assert 'evidence' not in denied and 'receipt' not in denied
            state['fault'] = None
            status, restored = http(base,'/query',TOKEN,{**body,'requestId':'after-fault'})
            assert status == 200 and restored['decision']=='EVIDENCE_FOUND'
            assert restored['receipt']['requestId']=='after-fault'
            assert state['calls']==2
            record_property('transportEvidence',json.dumps({'fault':fault,'rejected':denied,
                'recoveryReceipt':restored['receipt'],'scope':'CONTROLLED_HTTP_UPSTREAM'}))


@pytest.mark.parametrize('change', ['lease-revoked','lease-expired','source-permission',
    'product-permission','source-revoked','manifest-binding'])
def test_http_revocation_during_retrieval(ready, change, record_property):
    runtime, body, current, service, client = ready
    if change == 'source-revoked':
        current['lease'] = replace(current['lease'],
            context=replace(current['lease'].context,business_date='2026-10-31'))
        body = {**body,'businessDate':'2026-10-31'}
    entered, resume = threading.Event(), threading.Event()
    original = client.retrieve
    def blocked(*args):
        rows = original(*args)
        entered.set()
        assert resume.wait(5)
        return rows
    client.retrieve = blocked
    with listening(IsolatedServer(('127.0.0.1',0),handler(runtime))) as base:
        result = []
        worker = threading.Thread(target=lambda:result.append(http(base,'/query',TOKEN,body)))
        worker.start()
        try:
            assert entered.wait(5)
            if change=='lease-revoked': current['lease']=None
            elif change=='lease-expired':
                current['lease']=replace(current['lease'],expires=datetime.now(timezone.utc)-timedelta(seconds=1))
            else:
                core = service.core()
                try:
                    if change.endswith('permission'):
                        revision, digest = core._head(AUTHOR,'policy','current')
                        policy = core._get(AUTHOR,digest,'active-policy')
                        prefix = 'source:' if change=='source-permission' else 'product:'
                        policy['grants']=[g for g in policy['grants'] if not
                            (g['principal']==READER.principal and g['resource'].startswith(prefix))]
                        policy['revision']=revision+1
                        core.set_policy(AUTHOR,policy,revision)
                    elif change=='source-revoked':
                        manifest=core._get(READER,body['manifest'],'document-manifest')
                        core.activate_source(AUTHOR,manifest['sourceDigest'],'2026-10-31','REVOKED')
                    else:
                        # Simulates a different current binding, without publishing or touching the real DB.
                        revision,digest=core._head(AUTHOR,'document-binding',body['productId'])
                        binding=core._get(AUTHOR,digest,'document-binding')
                        binding['revision']=revision+1
                        binding['manifestDigest']='0'*64
                        with core.tx():
                            changed=core._put(AUTHOR,'document-binding',binding)
                            core._advance(AUTHOR,'document-binding',body['productId'],changed,revision)
                finally: core.close()
        finally:
            resume.set()
            worker.join(timeout=5)
        assert not worker.is_alive() and len(result)==1
        status, denied=result[0]
        assert status==403 and 'evidence' not in denied
        record_property('transportEvidence',json.dumps({'change':change,'response':denied,
            'scope':'CONTROLLED_IN_FLIGHT_REVOCATION'}))


def test_http_core_rechecked_after_session_resolver(ready):
    runtime,body,_,service,client=ready
    original=runtime.resolve_lease
    calls={'count':0}
    def resolve(token):
        calls['count']+=1
        if calls['count']==3:  # HTTP auth, query admission, final session recheck.
            core=service.core()
            try:
                revision,digest=core._head(AUTHOR,'policy','current')
                policy=core._get(AUTHOR,digest,'active-policy')
                policy['revision']=revision+1
                policy['grants']=[]
                core.set_policy(AUTHOR,policy,revision)
            finally: core.close()
        return original(token)
    runtime.resolve_lease=resolve
    with listening(IsolatedServer(('127.0.0.1',0),handler(runtime))) as base:
        status,value=http(base,'/query',TOKEN,body)
        assert status==403 and value['error']=='FORBIDDEN'


def test_readiness_never_overwrites_file_or_follows_link(tmp_path):
    target=tmp_path/'ready.json'
    record(target,{'status':'test'})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): record(target,{})
    link=tmp_path/'link.json'
    link.symlink_to(target)
    with pytest.raises(FileExistsError): record(link,{})
    assert json.loads(target.read_text())=={'status':'test'}


def test_wire_response_keeps_existing_session_contract(ready):
    runtime,body,_,_,_=ready
    session=runtime.session(TOKEN,{})
    assert set(session)=={'code','schemaVersion','sessionRef','productId','manifest'}
    result=runtime.query(TOKEN,body)
    validate_wire('queryResponse',result)
    assert 'sessionRef' not in result['receipt']


@pytest.mark.parametrize('case', ['reserved-port','missing-database','different-binding'])
def test_service_startup_rejects_unsafe_configuration(issued, tmp_path, monkeypatch, case):
    from m2.runtime_protocol import DIRECTORY, load_binding
    from m2.runtime_service import main
    _,_,policy,_,_,_=issued
    database=tmp_path/'core.sqlite'
    if case!='missing-database': database.touch()
    binding=load_binding(DIRECTORY/'h1a-binding.json')
    if case=='different-binding': binding['manifest']='0'*64
    binding_file=tmp_path/'binding.json'
    binding_file.write_text(json.dumps(binding))
    ready_file=tmp_path/'ready.json'
    monkeypatch.setattr(sys,'argv',['runtime_service','--database',str(database),'--authority',str(policy),
        '--binding',str(binding_file),'--private-config',str(tmp_path),'--ready-file',str(ready_file),
        '--port','61353' if case=='reserved-port' else '0'])
    expected={'reserved-port':'ISOLATED_PORT_REQUIRED','missing-database':'EXISTING_CORE_REQUIRED',
        'different-binding':'H1A_FIXED_BINDING_REQUIRED'}
    with pytest.raises(ValueError,match=expected[case]): main()
    assert not ready_file.exists()
