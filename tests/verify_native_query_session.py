"""Exactly two concurrent native read-only retrievals, without retry or LLM."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import threading

from knowledge_core.contracts import Rejected
from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from m2.history_runtime import ReadOnlyDocumentCore
from m2.product_release import read_release
from m2.ragflow import RagflowQuerySession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--private-config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    database = args.snapshot / 'core.sqlite'
    initial_bytes = sha256(database.read_bytes()).hexdigest()
    binding = json.loads((args.snapshot / 'binding.json').read_text())
    actor = Actor('m2-isolated', 'knowledge-agent', 'isolated-h1a-host-operator')
    context = BusinessContext('2026-10-31', 'CN-BJ', 'synthetic-bank', 'customer-service',
                              'evidence-query', 'frozen-synthetic-clock')
    descriptor = read_release(database, actor, context, binding['productId'], binding['manifest'], 'knowledge-factory-isolated')
    core = ReadOnlyDocumentCore(database)
    try:
        manifest = core._get(actor, binding['manifest'], 'document-manifest')
        index = core._get(actor, manifest['indexDigest'], 'document-index')
        receipt_count = core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone()[0]
    finally:
        core.close()
    questions = json.loads((Path(__file__).resolve().parents[1] / 'examples/products/synthetic-product-tests.json').read_text())[:2]
    session = RagflowQuerySession(args.private_config / 'local-credentials.json', args.private_config / 'http-setup.json')
    barrier = threading.Barrier(2)
    def attempt(case):
        client = None
        try:
            client = session()
            barrier.wait(timeout=10)
            evidence = DocumentCore._retrieve(index, case['question'], client)
            passed = any(e['clause'] == case['expectedClause'] for e in evidence)
            return {**case, 'status': 'PASSED' if passed else 'FAILED_EXPECTED_CLAUSE', 'evidence': evidence}
        except Exception as exc:
            return {**case, 'status': 'FAILED', 'error': exc.code if isinstance(exc, Rejected) else type(exc).__name__}
        finally:
            if client is not None: client.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, case) for case in questions]
            results = [future.result() for future in futures]
    finally:
        session.close()
    after = read_release(database, actor, context, binding['productId'], binding['manifest'], 'knowledge-factory-isolated')
    core = ReadOnlyDocumentCore(database)
    try:
        after_receipts = core.db.execute("SELECT count(*) FROM objects WHERE kind='document-receipt'").fetchone()[0]
    finally:
        core.close()
    root = Path(__file__).resolve().parents[1]
    record = {'schemaVersion': 'native-query-session-check.v0.1',
        'implementation': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'workingTreeDirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
        'manifestDigest': binding['manifest'], 'descriptorDigest': descriptor['descriptorDigest'],
        'upstream': 'REAL_RAGFLOW', 'hostAuthorization': 'NOT_AN_AGENT_ACCEPTANCE',
        'loginAttempts': session.login_attempts, 'scheduledReadOnlyRetrievals': 2,
        'automaticRetries': 0, 'modelCalls': 0, 'newCoreQueryReceipts': after_receipts - receipt_count,
        'snapshotBytesUnchanged': initial_bytes == sha256(database.read_bytes()).hexdigest(),
        'descriptorUnchanged': after == descriptor,
        'sessionClosed': session._closed and session._client is not None and session._client.token is None,
        'results': results}
    passed = (all(r['status'] == 'PASSED' for r in results) and record['loginAttempts'] == 1
        and record['snapshotBytesUnchanged'] and record['newCoreQueryReceipts'] == 0
        and record['descriptorUnchanged'] and record['sessionClosed'])
    record['status'] = 'PASSED_LIMITED_NATIVE_CONCURRENCY' if passed else 'FAILED'
    (args.output / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('status', 'loginAttempts', 'newCoreQueryReceipts', 'snapshotBytesUnchanged')}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
