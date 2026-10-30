"""Real HTTP acceptance on a backup of c293974's product, NOT Agent acceptance.

Synthetic Host files below are test fixtures for the frozen boundary. This is
not a second authority service and must never be imported by runtime_service.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
from urllib import request, error

from knowledge_core.documents import DocumentCore
from m2.acceptance import READER, AUTHOR, CONTEXT, CASES
from m2.runtime_protocol import DIRECTORY, CONTRACT_SHA256, load_binding, validate_wire


def http(base, path, token, body):
    headers = {'Content-Type':'application/json'}
    if token is not None: headers['Authorization'] = 'Bearer '+token
    req = request.Request(base+path, json.dumps(body).encode(), headers=headers)
    try:
        response = request.urlopen(req, timeout=90)
    except error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(262145)
        assert len(raw) <= 262144
        result = json.loads(raw)
        validate_wire('errorResponse' if response.status != 200 else
                      'queryResponse' if path == '/query' else 'sessionResponse', result)
        return response.status, result


def state_digest(database, include_history=False):
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as db:
        digest = sha256()
        for query in ("SELECT * FROM heads ORDER BY tenant,kind,name",
                      "SELECT * FROM activations ORDER BY tenant,source,effective",
                      "SELECT * FROM objects " + ("" if include_history else "WHERE kind!='document-receipt' ") + "ORDER BY tenant,digest"):
            for row in db.execute(query): digest.update(json.dumps(row, sort_keys=True).encode())
        return digest.hexdigest()


def private_json(path, value):
    # Fixture files only. The actual service has no write/issue operation.
    path.write_text(json.dumps(value))
    path.chmod(0o600)


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    binding = load_binding(DIRECTORY/'h1a-binding.json')
    report = {'schemaVersion':'knowledge-runtime-http-acceptance.v0.1', 'status':'FAILED',
        'scope':'REAL_HTTP_RUNTIME_AND_REAL_RAGFLOW_NOT_INSTALLED_AGENT',
        'hostAuthority':'SYNTHETIC_FILE_FIXTURE_NOT_HARNESS_HOST_ACCEPTANCE',
        'contractSha256':CONTRACT_SHA256, 'binding':binding, 'checks':[],
        'generativeModelCalls':0, 'cost':None, 'installationLock':None,
        'implementation':{name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('runtime_acceptance.py','runtime_service.py','harness_runtime.py','host_leases.py','runtime_protocol.py')}}
    before = state_digest(args.database)
    history_before = state_digest(args.database, include_history=True)
    database = output/'core-copy.sqlite'
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as source:
        with sqlite3.connect(database) as target: source.backup(target)
    database.chmod(0o600)
    lease_directory = output/'leases'
    lease_directory.mkdir(mode=0o700)
    policy = output/'synthetic-host-authority.json'
    config = dict(schemaVersion='knowledge-host-authority.v0.1', enabled=True, ownerRef='h1a-http-test-owner',
        principalId=READER.principal, tenant=READER.tenant, authority=READER.authority,
        subjectRef='synthetic-subject', productId=binding['productId'], manifest=binding['manifest'],
        context=asdict(CONTEXT), expiresAt=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),
        leaseDirectory=str(lease_directory))
    private_json(policy, config)
    token = secrets.token_urlsafe(48)
    lease_file = lease_directory/(sha256(token.encode()).hexdigest()+'.json')
    lease = dict(schemaVersion='knowledge-host-lease.v0.1', policyDigest=sha256(policy.read_bytes()).hexdigest(),
        ownerRef=config['ownerRef'], instanceId='synthetic-http-instance', sessionRef='synthetic-http-session',
        expiresAt=(datetime.now(timezone.utc)+timedelta(minutes=8)).isoformat())
    private_json(lease_file, lease)
    ready_file = output/'runtime-ready.json'
    log = (output/'runtime.log').open('wb')
    process = None
    def start(ready_path, port):
        child = subprocess.Popen([sys.executable,'-m','m2.runtime_service','--database',str(database),
            '--authority',str(policy),'--private-config',str(args.private_config.resolve()),
            '--port',str(port),'--ready-file',str(ready_path)],
            cwd=Path(__file__).resolve().parents[1], stdout=log, stderr=subprocess.STDOUT)
        try:
            until = time.monotonic()+15
            while not ready_path.exists():
                if child.poll() is not None or time.monotonic()>until: raise RuntimeError('RUNTIME_START_FAILED')
                time.sleep(.05)
            return child, json.loads(ready_path.read_text())
        except BaseException:
            child.terminate()
            child.wait(timeout=75)
            raise
    try:
        process, ready = start(ready_file, args.port)
        assert ready['pid'] == process.pid and ready['host'] == '127.0.0.1'
        assert ready['contractSha256'] == CONTRACT_SHA256 and ready['binding'] == binding
        report['runtime'] = ready
        base = 'http://127.0.0.1:'+str(ready['port'])
        def check(name, path, body, expected=200, credential=token, expected_error=None):
            status, value = http(base,path,credential,body)
            passed = status == expected and (expected_error is None or value.get('error') == expected_error)
            report['checks'].append({'name':name,'path':path,'httpStatus':status,'response':value,'passed':passed})
            assert passed, name
            return value
        check('current-session','/session',{})
        body = dict(schemaVersion='knowledge-query.v0.1',capabilityId='knowledge.evidence.search',
            productId=binding['productId'],manifest=binding['manifest'],businessDate=CONTEXT.business_date,
            principalId=READER.principal,subjectRef=config['subjectRef'],sessionRef=lease['sessionRef'],
            purpose=CONTEXT.purpose,requestId='http-acceptance-0',traceId='http-acceptance-trace',
            arguments={'question':CASES[0]['question']})
        for i, case in enumerate(CASES):
            query = {**body,'requestId':'http-acceptance-'+str(i),'arguments':{'question':case['question']}}
            value = check('real-ragflow-query-'+str(i),'/query',query)
            receipt = value['receipt']
            assert all(receipt[k] == query[k] for k in ('requestId','traceId','productId','manifest','businessDate'))
            report['checks'][-1]['requestContext'] = {k:query[k] for k in
                ('requestId','traceId','sessionRef','principalId','productId','manifest','businessDate')}
            assert receipt['receiptId'] == 'kr-'+receipt['coreReceiptDigest']
            assert case['expectedClause'] in [e['clause'] for e in value['evidence']]
            core = DocumentCore(database)
            try:
                stored = core.replay_document(READER,receipt['coreReceiptDigest'])
                assert stored['requestId']==query['requestId'] and stored['manifestDigest']==binding['manifest']
                assert stored['sourceDigest']==receipt['sourceDigest']
            finally: core.close()
        # Restart only this test process, retaining the same database and Host fixture.
        process.terminate()
        process.wait(timeout=75)
        assert process.returncode == 0
        report['firstStopReceipt'] = json.loads(ready_file.with_suffix('.stopped.json').read_text())
        ready_file = output/'runtime-restarted.json'
        process, restarted = start(ready_file, ready['port'])
        assert restarted['pid'] != ready['pid'] and restarted['binding'] == binding
        report['restartedRuntime'] = restarted
        check('session-after-process-restart','/session',{})
        check('real-query-after-process-restart','/query',{**body,'requestId':'http-after-restart'})
        core = DocumentCore(database)
        try:
            saved_receipt = report['checks'][1]['response']['receipt']['coreReceiptDigest']
            assert core.replay_document(READER,saved_receipt)['manifestDigest'] == binding['manifest']
            report['historicalReceiptReadableAfterRestart'] = True
        finally: core.close()
        for path, request_body in [('/query',body),('/session',{})]:
            check('missing-bearer'+path,path,request_body,403,None,'KNOWLEDGE_AUTH_REQUIRED')
            check('incorrect-bearer'+path,path,request_body,403,'wrong','KNOWLEDGE_AUTH_REQUIRED')
            private_json(lease_file,{**lease,'expiresAt':'2000-01-01T00:00:00Z'})
            check('expired-lease'+path,path,request_body,403,expected_error='KNOWLEDGE_AUTH_REQUIRED')
            private_json(lease_file,lease)
            lease_file.unlink()
            check('revoked-lease'+path,path,request_body,403,expected_error='KNOWLEDGE_AUTH_REQUIRED')
            private_json(lease_file,lease)
        for field, bad in [('manifest','0'*64),('sessionRef','other-session'),('principalId','other-reader'),
                           ('subjectRef','other-subject'),('purpose','publish'),
                           ('productId','other-product'),('businessDate','2026-11-01')]:
            check('spoof-'+field,'/query',{**body,field:bad},403,expected_error='KNOWLEDGE_CONTEXT_MISMATCH')
        check('invalid-query-type','/query',{**body,'arguments':{'question':False}},403)
        check('session-cannot-issue-identity','/session',{'principalId':'other-reader'},403)
        # Even a newly signed fixture lease cannot switch the service's pinned product.
        private_json(policy,{**config,'manifest':'0'*64})
        private_json(lease_file,{**lease,'policyDigest':sha256(policy.read_bytes()).hexdigest()})
        check('host-binding-mismatch','/session',{},403,expected_error='KNOWLEDGE_BINDING_MISMATCH')
        private_json(policy,config);private_json(lease_file,lease)
        incomplete_context = {k:v for k,v in config['context'].items() if k!='source'}
        private_json(policy,{**config,'context':incomplete_context})
        private_json(lease_file,{**lease,'policyDigest':sha256(policy.read_bytes()).hexdigest()})
        check('host-trusted-context-missing','/session',{},403,expected_error='KNOWLEDGE_AUTH_REQUIRED')
        private_json(policy,config);private_json(lease_file,lease)
        private_json(policy,{**config,'enabled':False})
        check('host-policy-revoked','/session',{},403,expected_error='KNOWLEDGE_AUTH_REQUIRED')
        private_json(policy,config)
        core = DocumentCore(database)
        try:
            manifest = core._get(READER,binding['manifest'],'document-manifest')
            source = core._get(READER,manifest['sourceDigest'],'source-revision')
            report['source'] = {'sourceDigest':manifest['sourceDigest'],'sourceId':source['id'],'revision':source['revision']}
            for prefix in ('source:', 'product:'):
                revision, digest = core._head(AUTHOR,'policy','current')
                original = core._get(AUTHOR,digest,'active-policy')
                updated = {**original,'revision':revision+1,'grants':[g for g in original['grants'] if not
                    (g['principal']==READER.principal and g['resource'].startswith(prefix))]}
                core.set_policy(AUTHOR,updated,revision)
                check('permission-revoked-'+prefix+'query','/query',body,403,expected_error='FORBIDDEN')
                check('permission-revoked-'+prefix+'session','/session',{},403,expected_error='FORBIDDEN')
                core.set_policy(AUTHOR,{**original,'revision':revision+2},revision+1)
                check('permission-restored-'+prefix,'/session',{})
            # An immutable activation cannot be overwritten on the same date.
            # Advance only the synthetic fixture's trusted date, on this database copy.
            latest = core.db.execute('SELECT MAX(effective) FROM activations WHERE tenant=? AND source=?',
                (READER.tenant,source['id'])).fetchone()[0]
            revoked_date = (datetime.fromisoformat(max(latest,CONTEXT.business_date))+timedelta(days=1)).date().isoformat()
            new_config = {**config,'context':{**config['context'],'business_date':revoked_date}}
            private_json(policy,new_config)
            private_json(lease_file,{**lease,'policyDigest':sha256(policy.read_bytes()).hexdigest()})
            check('source-valid-before-revocation','/session',{})
            core.activate_source(AUTHOR,manifest['sourceDigest'],revoked_date,'REVOKED')
            check('source-no-longer-effective-query','/query',{**body,'businessDate':revoked_date},403)
            check('source-no-longer-effective-session','/session',{},403)
        finally: core.close()
        assert before == state_digest(args.database)
        report.update(status='PASSED', originalGovernanceUnchanged=True)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=75)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=10)
                report['status']='FAILED_FORCED_STOP'
        log.close()
        report['exitCode'] = None if process is None else process.returncode
        stopped = ready_file.with_suffix('.stopped.json')
        report['stopReceipt'] = json.loads(stopped.read_text()) if stopped.exists() else None
        lease_file.unlink(missing_ok=True);policy.unlink(missing_ok=True)
        report['fixtureCredentialFilesRemoved'] = not lease_file.exists() and not policy.exists()
        report['originalGovernanceUnchanged'] = before == state_digest(args.database)
        report['originalHistoryAndObjectsUnchanged'] = history_before == state_digest(args.database, include_history=True)
        if not report['originalGovernanceUnchanged'] or not report['originalHistoryAndObjectsUnchanged']:
            report['status'] = 'FAILED_ORIGINAL_DATABASE_CHANGED'
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'checks':len(report['checks']),'report':str(output/'result.json')}))
    assert report['status']=='PASSED' and report['exitCode']==0 and report['stopReceipt']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--private-config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int,default=0)
    run(parser.parse_args())


if __name__ == '__main__': main()
