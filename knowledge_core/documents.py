"""Core-owned isolated document lifecycle, using Core's existing store and policy.

Network retrieval runs outside SQLite transactions. Authorization and binding are
checked both before sending and immediately before persisting/disclosing results.
Only exact original quotes are returned, never arbitrary upstream chunk bodies.
"""
import hashlib
import re
from datetime import datetime, timezone

from .core import Core, BusinessContext
from .contracts import Rejected, canonical, digest, text_digest
from .rules import in_scope
from . import document_contracts
from probes.documents.anchor_bridge import verify_bridge


def normal(text):
    return re.sub(r'\s+', '', text)


class DocumentCore(Core):
    def _put(self, actor, kind, body):
        if kind not in document_contracts.SCHEMAS:
            return super()._put(actor, kind, body)
        # Additive formats share M0's immutable store; the frozen M0 stays byte-identical.
        sha = document_contracts.validate(kind, body)
        self.db.execute('INSERT OR IGNORE INTO objects VALUES(?,?,?,?)',
                        (actor.tenant, sha, kind, canonical(body)))
        if 'id' in body and 'revision' in body:
            key = (actor.tenant, kind, body['id'], body['revision'])
            prior = self.db.execute('SELECT digest FROM identities WHERE tenant=? AND kind=? AND name=? AND revision=?',key).fetchone()
            if prior and prior[0] != sha:
                raise Rejected('IMMUTABLE_REVISION')
            self.db.execute('INSERT OR IGNORE INTO identities VALUES(?,?,?,?,?)',(*key,sha))
        return sha

    def register_document_index(self, actor, source_digest, raw, bridge, index, clauses):
        actor.require('artifact.produce')
        source = self._source_access(actor, source_digest)
        verify_bridge(raw, source, bridge, digest(bridge))
        # Exact content comes from verified native anchors, not a producer's labels.
        expected = {}
        for mapping in bridge['mappings']:
            expected.setdefault(mapping['clause'], []).append(mapping['anchor']['quote'])
        texts = {key: '\n'.join(parts) for key, parts in expected.items()}
        if clauses != [{'clause': k, 'text': v} for k, v in texts.items()]:
            raise Rejected('CLAUSE_SOURCE_MISMATCH')
        seen, covered = set(), set()
        for chunk in index['chunks']:
            if chunk['id'] in seen or text_digest(chunk['text']) != chunk['textDigest']:
                raise Rejected('INDEX_CHUNK_INVALID')
            seen.add(chunk['id'])
            matches = [key for key, quote in texts.items() if normal(quote) in normal(chunk['text'])]
            if matches != chunk['clauses']:
                raise Rejected('INDEX_ANCHOR_MISMATCH')
            covered.update(matches)
        if covered != set(texts):
            raise Rejected('INDEX_COVERAGE_INCOMPLETE')
        body = {'schemaVersion':'document-index.v0.1', 'sourceDigest':source_digest,
                'originalHtml':raw.decode('utf-8'), 'originalDigest':hashlib.sha256(raw).hexdigest(),
                'bridge':bridge, 'bridgeDigest':digest(bridge), 'index':index, 'clauses':clauses}
        with self.tx():
            return self._put(actor, 'document-index', body)

    def create_document_candidate(self, actor, candidate_digest, index_digest, tests):
        actor.require('artifact.produce')
        with self.tx():
            candidate, recipe, artifacts, rules = self._parts(actor, candidate_digest)
            index = self._get(actor, index_digest, 'document-index')
            if rules or recipe['processes'] != ['document']:
                raise Rejected('DOCUMENT_ONLY_REQUIRED')
            if recipe['sourceDigests'] != [index['sourceDigest']]:
                raise Rejected('INDEX_SOURCE_MISMATCH')
            if not tests or any(t['expectedClause'] not in {c['clause'] for c in index['clauses']} for t in tests):
                raise Rejected('RETRIEVAL_GOLD_INVALID')
            self._source_access(actor, index['sourceDigest'])
            return self._put(actor, 'document-candidate', {
                'schemaVersion':'document-candidate.v0.1', 'productId':candidate['productId'],
                'coreCandidateDigest':candidate_digest, 'indexDigest':index_digest, 'tests':tests})

    def _document_parts(self, actor, candidate_digest):
        candidate = self._get(actor, candidate_digest, 'document-candidate')
        core_candidate, recipe, artifacts, rules = self._parts(actor, candidate['coreCandidateDigest'])
        index = self._get(actor, candidate['indexDigest'], 'document-index')
        source = self._source_access(actor, index['sourceDigest'])
        verify_bridge(index['originalHtml'].encode(), source, index['bridge'], index['bridgeDigest'])
        return candidate, recipe, artifacts, index

    @staticmethod
    def _retrieve(index, question, client):
        pinned = index['index']
        try:
            rows = client.retrieve(pinned['datasetId'], pinned['documentId'], question)
        except Rejected:
            raise
        except Exception:
            raise Rejected('RETRIEVAL_UNAVAILABLE') from None
        if not isinstance(rows, list) or len(rows) > 3:
            raise Rejected('RETRIEVAL_RESPONSE_INVALID')
        chunks = {c['id']: c for c in pinned['chunks']}
        clauses = {c['clause']: c['text'] for c in index['clauses']}
        found, evidence = set(), []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'id', 'text', 'documentId'}:
                raise Rejected('RETRIEVAL_RESPONSE_INVALID')
            chunk = chunks.get(row['id'])
            if (not chunk or row['documentId'] != pinned['documentId']
                    or not isinstance(row['text'], str) or text_digest(row['text']) != chunk['textDigest']):
                raise Rejected('RETRIEVAL_INDEX_MISMATCH')
            for clause in chunk['clauses']:
                if clause in found:
                    continue
                found.add(clause)
                evidence.append({'clause':clause, 'quote':clauses[clause],
                    'originalDigest':index['originalDigest'], 'chunkId':chunk['id'],
                    'anchors':[m['anchor'] for m in index['bridge']['mappings'] if m['clause']==clause]})
        return evidence

    def validate_document(self, actor, candidate_digest, client):
        actor.require('candidate.validate')
        candidate, _, _, index = self._document_parts(actor, candidate_digest)
        core_validation = self.validate_candidate(actor, candidate['coreCandidateDigest'])
        results = []
        for case in candidate['tests']:
            try:
                evidence = self._retrieve(index, case['question'], client)
                actual = [e['clause'] for e in evidence]
                failure = None
            except Rejected as exc:
                actual, failure = [], exc.code
            results.append({**case, 'actualClauses':actual, 'error':failure,
                            'passed':failure is None and case['expectedClause'] in actual})
        with self.tx():
            self._document_parts(actor, candidate_digest)
            return self._put(actor, 'document-validation', {
                'schemaVersion':'document-validation.v0.1', 'candidateDigest':candidate_digest,
                'coreValidationDigest':core_validation,
                'passed':self._get(actor, core_validation, 'validation')['passed'] and all(r['passed'] for r in results),
                'results':results})

    def _document_valid(self, actor, candidate_digest, validation_digest):
        candidate = self._get(actor, candidate_digest, 'document-candidate')
        validation = self._get(actor, validation_digest, 'document-validation')
        if validation['candidateDigest'] != candidate_digest or not validation['passed']:
            raise Rejected('DOCUMENT_VALIDATION_FAILED_OR_MISMATCH')
        self._valid_result(actor, candidate['coreCandidateDigest'], validation['coreValidationDigest'])

    def approve_document(self, actor, candidate_digest, validation_digest, reason):
        actor.require('document.approve')
        with self.tx():
            self._document_parts(actor, candidate_digest)
            self._document_valid(actor, candidate_digest, validation_digest)
            return self._put(actor, 'document-approval', {
                'schemaVersion':'document-approval.v0.1', 'candidateDigest':candidate_digest,
                'validationDigest':validation_digest, 'actor':actor.principal,
                'authorityRef':actor.authority, 'decision':'ISOLATED_TEST_APPROVAL', 'reason':reason})

    def publish_document(self, actor, candidate_digest, validation_digest, approval_digest, revision):
        actor.require('manifest.publish')
        with self.tx():
            candidate, recipe, _, index = self._document_parts(actor, candidate_digest)
            self._document_valid(actor, candidate_digest, validation_digest)
            approval = self._get(actor, approval_digest, 'document-approval')
            if approval['candidateDigest'] != candidate_digest or approval['validationDigest'] != validation_digest:
                raise Rejected('DOCUMENT_APPROVAL_MISMATCH')
            if self._head(actor, 'recipe', recipe['id'])[1] != digest(recipe):
                raise Rejected('DRAFT_CHANGED_REVALIDATE')
            return self._put(actor, 'document-manifest', {
                'schemaVersion':'document-manifest.v0.1', 'id':candidate['productId'], 'revision':revision,
                'productId':candidate['productId'], 'candidateDigest':candidate_digest,
                'validationDigest':validation_digest, 'approvalDigest':approval_digest,
                'indexDigest':candidate['indexDigest'], 'sourceDigest':index['sourceDigest'],
                'mode':'M2_ISOLATED_DOCUMENT'})

    def bind_document(self, actor, manifest_digest, expected_revision):
        actor.require('binding.manage')
        with self.tx():
            manifest = self._get(actor, manifest_digest, 'document-manifest')
            binding = {'schemaVersion':'document-binding.v0.1','productId':manifest['productId'],
                       'revision':expected_revision+1,'manifestDigest':manifest_digest,'versionPolicy':'PINNED'}
            sha = self._put(actor, 'document-binding', binding)
            self._advance(actor, 'document-binding', manifest['productId'], sha, expected_revision)
            return sha

    def _query_binding(self, actor, product_id, expected_manifest, context):
        if not isinstance(context, BusinessContext):
            raise Rejected('TRUSTED_CONTEXT_REQUIRED')
        host = context.facts()
        self._permit(actor, 'product:'+product_id, 'consume')
        _, sha = self._head(actor, 'document-binding', product_id)
        binding = self._get(actor, sha, 'document-binding')
        if binding['manifestDigest'] != expected_manifest:
            raise Rejected('MANIFEST_MISMATCH')
        manifest = self._get(actor, expected_manifest, 'document-manifest')
        _, _, artifacts, index = self._document_parts(actor, manifest['candidateDigest'])
        self._source_current(actor, index['sourceDigest'], context.business_date)
        if any(not in_scope(a['scope'], host) for a in artifacts):
            raise Rejected('KNOWLEDGE_NOT_APPLICABLE')
        return sha, manifest, index, host

    def query_document(self, actor, product_id, manifest_digest, context, question, request_id, trace_id, client):
        if not isinstance(question, str) or not 1 <= len(question) <= 1000:
            raise Rejected('INVALID_QUESTION')
        for value in (request_id, trace_id):
            if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}', value):
                raise Rejected('INVALID_REQUEST_ID')
        with self.tx():
            binding, manifest, index, host = self._query_binding(actor, product_id, manifest_digest, context)
        evidence = self._retrieve(index, question, client)
        with self.tx():
            current, _, _, _ = self._query_binding(actor, product_id, manifest_digest, context)
            if current != binding:
                raise Rejected('BINDING_CHANGED')
            receipt = {'schemaVersion':'document-receipt.v0.1', 'requestId':request_id, 'traceId':trace_id,
                'principal':actor.principal, 'productId':product_id, 'manifestDigest':manifest_digest,
                'indexDigest':manifest['indexDigest'], 'sourceDigest':manifest['sourceDigest'],
                'bindingDigest':binding, 'policyDigest':self._head(actor,'policy','current')[1],
                'hostAuthority':actor.authority, 'businessContextSource':context.source,
                'question':question, 'host':host, 'result':{'decision':'EVIDENCE_FOUND' if evidence else 'EVIDENCE_NOT_FOUND',
                'evidence':evidence}, 'createdAt':datetime.now(timezone.utc).isoformat(), 'mode':'M2_ISOLATED_DOCUMENT'}
            sha = self._put(actor, 'document-receipt', receipt)
        return {'receiptDigest':sha, **receipt}

    def replay_document(self, actor, receipt_digest):
        with self.tx():
            receipt = self._get(actor, receipt_digest, 'document-receipt')
            self._permit(actor,'product:'+receipt['productId'],'history')
            if receipt['principal'] != actor.principal:
                self._permit(actor,'receipt:'+receipt_digest,'history')
            self._source_access(actor,receipt['sourceDigest'])
            return {'receiptDigest':receipt_digest, 'replay':True, **receipt}
