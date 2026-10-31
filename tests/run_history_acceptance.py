"""Isolated real-HTTP history acceptance; synthetic Host, actual saved receipt.

Never issues authority for Harness. Private fixture files live in a temporary
directory and are destroyed; the input database and Harness evidence are read-only.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from knowledge_core.contracts import canonical, digest
from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from m2.history_runtime import MAX_RESPONSE, SCHEMA_SHA256
from m2.runtime_service import record, code_identity
from tests.test_history_runtime import host_files, refresh_authority, private_json, history_request, TOKEN

MANIFEST = '8f5dc67b321edb48b0636581d63834c62b175a90d5dcad624b6460ff989606f3'
RECEIPT = '6bfafa7dbce44296561fad0b99feea70a7e07f5b6baae012eaa9f4e271ae068e'
INSTANCE = '4553dde6-4b96-4828-a934-0c1eb8ea3ce2'
AGENT = 'agent-60b8171a34ef479c'
LOCK = '2968aec67089c36591986e6ba8ac18e4c59e42ef15f14969f1347d3a3468ef5f'


def snapshot(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        state = {table: db.execute('SELECT * FROM '+table+' ORDER BY 1,2,3').fetchall()
                 for table in ('objects', 'heads', 'identities', 'activations')}
        receipts = db.execute("SELECT tenant,digest,body FROM objects WHERE kind='document-receipt' ORDER BY tenant,digest").fetchall()
        return {'stateDigest': digest(state), 'receiptDigest': digest(receipts), 'receiptCount': len(receipts)}
    finally: db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-database', type=Path, required=True)
    parser.add_argument('--joint-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    source_before = snapshot(args.source_database)
    database = args.output / 'core.sqlite'
    source = sqlite3.connect(args.source_database.resolve().as_uri()+'?mode=ro', uri=True)
    target = sqlite3.connect(database)
    source.backup(target)
    source.close()
    target.close()
    initial = snapshot(database)
    core = DocumentCore(database)
    row = core.db.execute("SELECT tenant,body FROM objects WHERE digest=? AND kind='document-receipt'", (RECEIPT,)).fetchone()
    tenant, saved = row[0], json.loads(row[1])
    assert digest(saved) == RECEIPT and saved['manifestDigest'] == MANIFEST
    actor = Actor(tenant, saved['principal'], 'synthetic-history-acceptance', frozenset({'policy.manage', 'binding.manage', 'source.activate'}))
    body = history_request({**saved, 'receiptDigest': RECEIPT}, core._get(actor, saved['sourceDigest'], 'source-revision'))
    lines = (args.joint_evidence/'query-events.sse').read_text().splitlines()
    values = [json.loads(line[6:]) for line in lines if line.startswith('data: ')]
    display = next(v['value'] for v in values if v.get('name') == 'finance.display')
    archive = json.loads((args.joint_evidence/'answer-archive-integrity.json').read_bytes())
    assert display['buildId'] == AGENT and display['instanceId'] == INSTANCE
    assert archive['instanceId'] == INSTANCE and archive['runtimeLockDigest'] == LOCK
    assert display['answerArchive']['digest'] == archive['sha256']
    original = display['toolResults'][0]['data']['result']
    assert original['knowledgeReceipt']['coreReceiptDigest'] == RECEIPT
    expected_query = {'code': 0, 'decision': original['decision'], 'evidence': original['evidence'], 'receipt': original['knowledgeReceipt']}
    revision, policy_sha = core._head(actor, 'policy', 'current')
    baseline_policy = core._get(actor, policy_sha, 'active-policy')
    results = []
    process = None
    ready = args.output/'ready.json'
    log = (args.output/'service.log').open('xb')
    before = snapshot(database)
    try:
        with tempfile.TemporaryDirectory(prefix='history-host-fixture-') as temporary:
            authority, lease = host_files(Path(temporary), {**saved, 'receiptDigest': RECEIPT},
                                          principal=saved['principal'], tenant=tenant)
            command = [sys.executable, '-m', 'm2.history_service', '--database', str(database),
                '--authority', str(authority), '--product', saved['productId'], '--manifest', MANIFEST,
                '--port', '0', '--ready-file', str(ready)]
            process = subprocess.Popen(command, stdout=log, stderr=log)
            for _ in range(100):
                if ready.exists(): break
                if process.poll() is not None: raise RuntimeError('HISTORY_PROCESS_EXITED')
                time.sleep(.1)
            metadata = json.loads(ready.read_bytes())
            def post(name, expected_status, request_body=None, token=TOKEN, expected_error=None):
                start = snapshot(database)
                connection = http.client.HTTPConnection('127.0.0.1', metadata['port'], timeout=10)
                request_body = request_body or body
                try:
                    connection.request('POST', '/history/read', json.dumps(request_body).encode(),
                        {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
                    reply = connection.getresponse()
                    status, value = reply.status, json.loads(reply.read())
                finally: connection.close()
                end = snapshot(database)
                passed = status == expected_status and start == end
                if expected_error: passed = passed and value == {'code': expected_status, 'error': expected_error}
                if status == 200:
                    passed = passed and value['savedReceipt'] == saved and value['queryResponse'] == expected_query
                evidence = {'name': name, 'passed': passed, 'httpStatus': status, 'expectedStatus': expected_status,
                    'request': request_body, 'response': value, 'before': start, 'after': end}
                record(args.output/(name+'.json'), evidence)
                results.append({'name': name, 'passed': passed, 'httpStatus': status})
                return value
            def policy_with(grants):
                rev, _ = core._head(actor, 'policy', 'current')
                core.set_policy(actor, {**baseline_policy, 'revision': rev+1, 'grants': grants}, rev)
            grants = baseline_policy['grants']
            post('saved-stopped-instance', 200)
            post('repeat-no-reexecution', 200)
            post('forged-bearer', 403, token='wrong-'+'z'*40, expected_error='HISTORY_AUTH_REQUIRED')
            refresh_authority(authority, lease, allowedReceiptDigests=['0'*64])
            post('host-receipt-denied', 403, expected_error='HISTORY_FORBIDDEN')
            refresh_authority(authority, lease, allowedReceiptDigests=[RECEIPT])
            post('manifest-mismatch', 409, {**body, 'expected': {**body['expected'], 'manifest': '0'*64}}, expected_error='HISTORY_REFERENCE_MISMATCH')
            view = json.loads(lease.read_bytes())
            private_json(lease, {**view, 'expiresAt': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()})
            post('expired-history-lease', 403, expected_error='HISTORY_AUTH_REQUIRED')
            private_json(lease, view)
            private_json(lease, {**view, 'schemaVersion': 'knowledge-host-lease.v0.1'})
            post('run-lease-wrong-type', 403, expected_error='HISTORY_AUTH_REQUIRED')
            private_json(lease, view)
            private_json(lease, {**view, 'policyDigest': '0'*64})
            post('forged-history-lease', 403, expected_error='HISTORY_AUTH_REQUIRED')
            private_json(lease, view)
            for name, prefix in [('source-revoked', 'source:'), ('product-history-revoked', 'product:')]:
                policy_with([g for g in grants if not (g['principal'] == saved['principal'] and g['resource'].startswith(prefix))])
                post(name, 403, expected_error='HISTORY_FORBIDDEN')
                policy_with(grants)
            refresh_authority(authority, lease, principalId='history-fixture-delegate')
            delegated = grants + [{**g, 'principal': 'history-fixture-delegate'} for g in grants if g['principal'] == saved['principal']]
            policy_with(delegated)
            post('cross-principal-no-exact-grant', 403, expected_error='HISTORY_FORBIDDEN')
            policy_with(delegated + [{'principal': 'history-fixture-delegate', 'resource': 'receipt:'+RECEIPT, 'actions': ['history']}])
            post('cross-principal-exact-host-and-core-grant', 200)
            policy_with(delegated)
            post('exact-receipt-grant-revoked', 403, expected_error='HISTORY_FORBIDDEN')
            policy_with(grants)
            refresh_authority(authority, lease, principalId=saved['principal'])
            post('authorization-restored', 200)
            # Additional synthetic oversized receipt on this test copy only.
            oversized = json.loads(json.dumps(saved))
            oversized['result']['syntheticOversizeDiagnostic'] = 'x'*MAX_RESPONSE
            with core.tx(): large_sha = core._put(actor, 'document-receipt', oversized)
            refresh_authority(authority, lease, allowedReceiptDigests=[large_sha])
            post('oversized-complete-response', 413, {**body, 'coreReceiptDigest': large_sha}, expected_error='HISTORY_RESPONSE_LIMIT')
            refresh_authority(authority, lease, allowedReceiptDigests=[RECEIPT])
            with core.tx():
                altered = core._get(actor, MANIFEST, 'document-manifest')
                altered['revision'] += 1
                new_manifest = core._put(actor, 'document-manifest', altered)
            binding_revision, _ = core._head(actor, 'document-binding', saved['productId'])
            core.bind_document(actor, new_manifest, binding_revision)
            core.activate_source(actor, saved['sourceDigest'], '2099-01-01', state='REVOKED')
            try:
                core._source_current(actor, saved['sourceDigest'], '2099-01-02')
            except Rejected as exc:
                assert exc.code == 'SOURCE_SUPERSEDED_OR_REVOKED'
            else:
                raise AssertionError('Test source must be inactive for future consumption')
            post('old-manifest-inactive-source-historical-read', 200)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.close()
        core.close()
    stopped = json.loads(ready.with_suffix('.stopped.json').read_bytes())
    final = snapshot(database)
    source_after = snapshot(args.source_database)
    report = {'scope': 'ACTUAL_SAVED_CORE_EVIDENCE_HTTP_WITH_SYNTHETIC_HOST_ON_DATABASE_COPY_NOT_HARNESS_UI_ACCEPTANCE',
        'codeIdentity': code_identity(), 'serviceIdentity': metadata, 'schemaSha256': SCHEMA_SHA256,
        'agent': AGENT, 'instance': INSTANCE, 'installationLockSha256': LOCK, 'manifest': MANIFEST,
        'coreReceiptDigest': RECEIPT, 'originalHarnessEvidenceSha256': sha256((args.joint_evidence/'query-events.sse').read_bytes()).hexdigest(),
        'queryProjectionComparedToSavedHarnessToolResult': True, 'results': results,
        'sourceBefore': source_before, 'sourceAfter': source_after, 'copyInitial': initial, 'copyFinal': final,
        'testSetupNewSyntheticOversizeReceipts': 1, 'historyGeneratedQueryReceipts': 0,
        'sourceInactivityCheckBusinessDate': '2099-01-02',
        'zeroExecutionProof': 'Each HTTP attempt has identical full Core state before/after; only explicit test setup mutates copy.',
        'outboundConnectionAttempts': stopped['outboundAttempts'], 'ragflowCalls': 0, 'modelCalls': 0,
        'outageMethod': 'History process has no upstream configuration and rejects every socket.connect/getaddrinfo; shared RAGFlow not stopped.',
        'exitCode': process.returncode,
        'passed': all(r['passed'] for r in results) and source_before == source_after
                  and stopped['outboundAttempts'] == 0 and process.returncode == 0}
    record(args.output/'report.json', report)
    print(json.dumps({'passed': report['passed'], 'cases': len(results), 'report': str(args.output/'report.json')}))
    if not report['passed']: raise SystemExit(1)


if __name__ == '__main__':
    main()
