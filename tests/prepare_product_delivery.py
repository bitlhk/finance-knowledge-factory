"""Explicit fresh isolated fixture via existing lifecycle and real RAGFlow.

No Host credential issuance. Refuses existing output/database. The isolated Core
policy is test provisioning, not a production IAM grant or source modification.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import uuid

from knowledge_core.core import Actor, BusinessContext
from knowledge_core.documents import DocumentCore
from knowledge_core.contracts import Rejected
from m2.synthetic_context import AUTHOR, SCOPE
from m2.pipeline import produce
from m2.ragflow import Ragflow
from m2.product_release import read_release, SCHEMA_SHA256


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-config', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(__file__).resolve().parents[1]
    raw = (root / 'examples/products/synthetic-product-policy.html').read_bytes()
    tests = json.loads((root / 'examples/products/synthetic-product-tests.json').read_text())
    product = 'synthetic-product-policy-' + uuid.uuid4().hex[:12]
    reader = Actor('m2-isolated', 'knowledge-agent', 'isolated-h1a-host-operator')
    context = BusinessContext('2026-10-31', 'CN-BJ', 'synthetic-bank', 'customer-service',
                              'evidence-query', 'frozen-synthetic-clock')
    database = args.output / 'core.sqlite'
    core = DocumentCore(database)
    database.chmod(0o600)
    result = {'schemaVersion': 'product-delivery-preparation.v0.1', 'productId': product,
        'implementation': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'workingTreeDirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
        'schemaDigest': SCHEMA_SHA256, 'inputDigest': sha256(raw).hexdigest(),
        'approvalMeaning': 'ISOLATED_TEST_APPROVAL_NOT_BANK_APPROVED',
        'hostCredentialsCreated': 0, 'generativeModelCalls': 0,
        'corePolicyScope': 'NEW_ISOLATED_DATABASE_ONLY', 'status': 'STARTED'}
    try:
        grants = []
        for principal in (AUTHOR.principal, reader.principal):
            grants.extend([{'principal': principal, 'resource': 'product:' + product, 'actions': ['consume', 'history']},
                {'principal': principal, 'resource': 'source:' + product + '-source', 'actions': ['source_read']}])
        core.set_policy(AUTHOR, {'schemaVersion': 'active-policy.v0.1', 'revision': 1, 'grants': grants}, 0)
        client = Ragflow(args.private_config / 'local-credentials.json', args.private_config / 'http-setup.json')
        data = produce(core, AUTHOR, product, 1, raw, SCOPE, tests, [reader.principal], client)
        validation = core.validate_document(AUTHOR, data['candidateDigest'], client)
        validation_body = core._get(AUTHOR, validation, 'document-validation')
        write(args.output / 'validation.json', validation_body)
        if not validation_body['passed']:
            raise Rejected('DOCUMENT_VALIDATION_FAILED')
        approval = core.approve_document(AUTHOR, data['candidateDigest'], validation,
            'Synthetic isolated product delivery fixture; not business approval')
        core.activate_source(AUTHOR, data['sourceDigest'], '2026-01-01')
        manifest = core.publish_document(AUTHOR, data['candidateDigest'], validation, approval, 1)
        core.bind_document(AUTHOR, manifest, 0)
        descriptor = read_release(database, reader, context, product, manifest, 'knowledge-factory-isolated')
        write(args.output / 'release.json', descriptor)
        write(args.output / 'binding.json', {'schemaVersion': 'knowledge-runtime-binding.v0.1',
            'productId': product, 'manifest': manifest, 'productionBaseline': result['implementation']})
        write(args.output / 'manifest.json', core._get(AUTHOR, manifest, 'document-manifest'))
        write(args.output / 'host-context-requirements.json', {'tenant': reader.tenant,
            'principalId': reader.principal, 'authority': reader.authority, 'context': asdict(context),
            'note': 'Contract example only, not a Host authority file or credential'})
        # Real retrieval smoke on the new snapshot, not the old H1a database.
        receipt = core.query_document(reader, product, manifest, context, tests[0]['question'],
            'product-delivery-smoke', 'product-delivery-trace', client)
        if not any(e['clause'] == '第一条' for e in receipt['result']['evidence']):
            raise Rejected('SMOKE_EVIDENCE_MISSING')
        write(args.output / 'query-receipt.json', receipt)
        result.update(status='ISOLATED_RELEASE_READY_NOT_BUILDER_ACCEPTANCE', manifestDigest=manifest,
            descriptorDigest=descriptor['descriptorDigest'], coreReceiptDigest=receipt['receiptDigest'],
            validationPassed=sum(r['passed'] for r in validation_body['results']),
            validationTotal=len(validation_body['results']), ragflowOperations=client.operations,
            retainedResources='New synthetic RAGFlow index retained for Harness verification')
    except Exception as exc:
        result.update(status='FAILED', error=exc.code if isinstance(exc, Rejected) else type(exc).__name__)
        write(args.output / 'preparation.json', result)
        raise SystemExit('Preparation failed; sanitized record retained') from None
    finally:
        core.close()
    write(args.output / 'preparation.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'productId', 'manifestDigest', 'descriptorDigest')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
