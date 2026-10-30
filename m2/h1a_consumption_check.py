"""Consumption boundary check against the existing M2 product, not an Agent test."""
import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess

from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from m2.acceptance import AUTHOR, READER, CONTEXT, CASES
from m2.harness_runtime import Lease, Runtime
from m2.ragflow import Ragflow

MANIFEST = '8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3'
PRODUCT = 'run-39d069d400924257a857cfa7ec64917b'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--database', type=Path, required=True)
    ap.add_argument('--private-config', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {'schemaVersion': 'h1a-core-consumption-check.v0.1', 'status': 'FAILED',
        'scope': 'CORE_PROTOCOL_NOT_BUILDER_INSTALL_OR_AGENT_UI',
        'productionBaseline': 'c2939742f211a1ed363dc792d3602d0098765a04',
        'adapterParentCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'implementation': {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ('m2/harness_runtime.py', 'm2/h1a_consumption_check.py', 'knowledge_core/documents.py')},
        'product': PRODUCT, 'manifest': MANIFEST, 'checks': [], 'modelCalls': 0, 'cost': None,
        'installationLock': None, 'agentUi': 'NOT_RUN'}
    credential = secrets.token_urlsafe(48)
    lease = Lease(READER, CONTEXT, 'synthetic-subject', 'h1a-consumption-check', PRODUCT,
                  MANIFEST, datetime.now(timezone.utc)+timedelta(minutes=10))
    client = None
    core = DocumentCore(args.database)
    try:
        before = core.db.execute('SELECT * FROM heads ORDER BY tenant,kind,name').fetchall()
        activations = core.db.execute('SELECT * FROM activations ORDER BY tenant,source,effective').fetchall()
        manifest = core._get(READER, MANIFEST, 'document-manifest')
        assert manifest['productId'] == PRODUCT
        report['source'] = core._get(READER, manifest['sourceDigest'], 'source-revision')
        def clients():
            nonlocal client
            client = Ragflow(args.private_config/'local-credentials.json', args.private_config/'http-setup.json')
            return client
        runtime = Runtime(args.database, lambda token: lease if secrets.compare_digest(token, credential) else None, clients)
        def request(case, index):
            return {'schemaVersion':'knowledge-query.v0.1','capabilityId':'knowledge.evidence.search',
                'productId':PRODUCT,'manifest':MANIFEST,'businessDate':CONTEXT.business_date,
                'principalId':READER.principal,'subjectRef':lease.subject,'sessionRef':lease.session,
                'purpose':CONTEXT.purpose,'requestId':f'h1a-consume-{args.output.name}-{index}',
                'traceId':f'h1a-trace-{args.output.name}', 'arguments':{'question':case['question']}}
        for index, case in enumerate(CASES):
            body = request(case,index)
            result = runtime.query(credential, body)
            check = {'case':case,'response':result,'nativeOperations':client.operations,
                     'passed':case['expectedClause'] in [e['clause'] for e in result['evidence']]}
            report['checks'].append(check)
            assert check['passed']
        # Destructive negative states use an exact SQLite backup, never mutate 61353.
        isolated = args.output/'negative-copy.sqlite'
        destination = sqlite3.connect(isolated)
        core.db.backup(destination)
        destination.close()
        report['negativeState'] = 'SQLITE_BACKUP_OF_REAL_PRODUCT_NOT_ORIGINAL_SERVICE'
        def no_upstream():
            raise AssertionError('Unauthorized request reached client construction')
        isolated_runtime = Runtime(isolated, lambda token: lease if token == credential else None, no_upstream)
        def denied(name, call, expected):
            try: call()
            except Rejected as exc:
                report['checks'].append({'case':name,'actual':exc.code,'expected':expected,'passed':exc.code==expected})
                assert exc.code == expected
            else: raise AssertionError('Expected denial')
        body = request(CASES[0], 'negative')
        denied('manifest-mismatch', lambda: isolated_runtime.query(credential,{**body,'manifest':'0'*64}), 'KNOWLEDGE_CONTEXT_MISMATCH')
        denied('unauthenticated', lambda: isolated_runtime.query('wrong',body), 'KNOWLEDGE_AUTH_REQUIRED')
        original_lease = lease
        lease = replace(lease, context=replace(CONTEXT,source=''))
        denied('missing-trusted-context',lambda:isolated_runtime.query(credential,body),'TRUSTED_CONTEXT_REQUIRED')
        lease = original_lease
        copy = DocumentCore(isolated)
        try:
            revision, sha = copy._head(AUTHOR,'policy','current')
            policy = copy._get(AUTHOR,sha,'active-policy')
            policy['revision'] = revision+1
            policy['grants'] = [g for g in policy['grants'] if not
                (g['principal']==READER.principal and g['resource']=='source:'+PRODUCT+'-source')]
            copy.set_policy(AUTHOR,policy,revision)
            denied('source-revocation',lambda:isolated_runtime.query(credential,body),'FORBIDDEN')
        finally: copy.close()
        assert before == core.db.execute('SELECT * FROM heads ORDER BY tenant,kind,name').fetchall()
        assert activations == core.db.execute('SELECT * FROM activations ORDER BY tenant,source,effective').fetchall()
        report.update(status='PASSED',existingBindingsUnchanged=True,existingActivationsUnchanged=True)
    finally:
        core.close()
        (args.output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':report['status'],'scope':report['scope'],'checks':len(report['checks'])}))


if __name__ == '__main__':
    main()
