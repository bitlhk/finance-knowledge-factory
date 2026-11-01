"""Core-owned isolated document lifecycle, using Core's existing store and policy.

Network retrieval runs outside SQLite transactions. Authorization and binding are
checked both before sending and immediately before persisting/disclosing results.
Only exact original quotes are returned, never arbitrary upstream chunk bodies.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

from .core import Core, BusinessContext
from .contracts import Rejected, canonical, digest, text_digest
from .rules import in_scope
from . import document_contracts
from knowledge_core.evidence.anchor_bridge import verify_bridge
from knowledge_core.evidence.html_evidence import analyze, map_retrieval_chunks
from knowledge_core.document_quality import evaluate_retrieval, validate_test_set
from knowledge_core.retrieval_quality import select as select_quality, trace_select
from knowledge_core.publication_quality import assess as assess_quality_gate


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
        seen = set()
        for chunk in index['chunks']:
            if chunk['id'] in seen or text_digest(chunk['text']) != chunk['textDigest']:
                raise Rejected('INDEX_CHUNK_INVALID')
            seen.add(chunk['id'])
        structure = analyze(raw)
        mapped = map_retrieval_chunks(structure['units'], index['chunks'])
        labels = {unit['unitId']: unit['label'] for unit in structure['units']
                  if unit['kind'] == 'ARTICLE'}
        expected_chunks = {chunk['chunkId']: [labels[value] for value in chunk['unitIds']]
                           for chunk in mapped['chunks']}
        if mapped['coverageBps'] != 10000 or mapped['incompleteUnitIds']:
            raise Rejected('INDEX_COVERAGE_INCOMPLETE')
        if any(chunk['clauses'] != expected_chunks.get(chunk['id'], []) for chunk in index['chunks']):
            raise Rejected('INDEX_ANCHOR_MISMATCH')
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

    def register_quality_profile(self, actor, profile_id, revision, config):
        actor.require('artifact.produce')
        required = {'retrieval', 'postRank', 'selectionThresholdBps', 'queryPlanner', 'supportPolicy'}
        if (not isinstance(config, dict) or set(config) != required
                or config['postRank'] != 'STRUCTURE_V0_2'
                or config['queryPlanner'] != 'DETERMINISTIC_FINANCIAL_V0_1'
                or config['supportPolicy'] != 'EVIDENCE_SUPPORT_V0_1'
                or type(config['selectionThresholdBps']) is not int):
            raise Rejected('QUALITY_PROFILE_INVALID')
        # The adapter performs the detailed retrieval-profile validation before use.
        with self.tx():
            return self._put(actor, 'document-quality-profile', {
                'schemaVersion':'document-quality-profile.v0.1', 'id':profile_id,
                'revision':revision, 'config':config})

    def register_quality_test_set(self, actor, candidate_digest, test_set, revision):
        actor.require('candidate.validate')
        candidate, _, _, index = self._document_parts(actor, candidate_digest)
        validate_test_set(test_set, {item['clause'] for item in index['clauses']})
        if test_set['sourceDigest'] != index['sourceDigest']:
            raise Rejected('QUALITY_TEST_SET_SOURCE_MISMATCH')
        with self.tx():
            self._document_parts(actor, candidate_digest)
            return self._put(actor, 'document-quality-test-set', {
                'schemaVersion':'document-quality-test-set.v0.1', 'id':test_set['id'],
                'revision':revision, 'candidateDigest':candidate_digest, 'testSet':test_set})

    def evaluate_quality_retrieval(self, actor, candidate_digest, profile_digest,
                                   test_set_digest, client):
        actor.require('candidate.validate')
        with self.tx():
            _, _, _, index = self._document_parts(actor, candidate_digest)
            profile = self._get(actor, profile_digest, 'document-quality-profile')
            test_object = self._get(actor, test_set_digest, 'document-quality-test-set')
        if test_object['candidateDigest'] != candidate_digest:
            raise Rejected('QUALITY_TEST_SET_CANDIDATE_MISMATCH')
        pinned = index['index']
        indexed = {chunk['id']: chunk for chunk in pinned['chunks']}
        rows = []
        for case in test_object['testSet']['cases']:
            started = datetime.now(timezone.utc)
            try:
                trace = trace_select(client, pinned['datasetId'], pinned['documentId'],
                                     case['question'], profile['config'])
            except Rejected:
                raise
            except Exception:
                raise Rejected('QUALITY_RETRIEVAL_UNAVAILABLE') from None
            def record(item, stage, decision, reasons):
                chunk = indexed.get(item.get('id'))
                if (chunk is None or item.get('documentId') != pinned['documentId']
                        or item.get('text') != chunk['text']
                        or text_digest(item['text']) != chunk['textDigest']):
                    raise Rejected('QUALITY_RETRIEVAL_INDEX_MISMATCH', case['caseId'])
                return {'stage':stage, 'rank':item['rank'], 'chunkId':item['id'],
                        'clauses':chunk['clauses'], 'scoreBps':item.get('scoreBps'),
                        'termScoreBps':item.get('termScoreBps'),
                        'vectorScoreBps':item.get('vectorScoreBps'),
                        'postRankScoreBps':item.get('postRankScoreBps'),
                        'decision':decision, 'reasons':reasons}
            stages = {
                'retrieved':[record(item, 'RETRIEVED', 'CANDIDATE',
                    ['returned by pinned retrieval profile']) for item in trace['retrieved']],
                'ranked':[record(item, 'RANKED', 'CANDIDATE',
                    ['ordered by pinned post-ranker']) for item in trace['ranked']],
                'filtered':[record(item, 'FILTERED', item['qualityDecision'], item['qualityReasons'])
                    for item in trace['filtered']],
                'selected':[record(item, 'SELECTED', 'SELECT',
                    ['within first three supported candidates']) for item in trace['selected']]}
            elapsed = max(0, round((datetime.now(timezone.utc) - started).total_seconds() * 1000))
            rows.append({'caseId':case['caseId'], 'latencyMs':elapsed, 'stages':stages,
                         'candidates':stages['selected']})
        recomputed = evaluate_retrieval(test_object['testSet'], rows,
            {'name': profile['id'], **profile['config']},
            pinned['engineIdentity'], pinned['embeddingIdentity'])
        with self.tx():
            self._document_parts(actor, candidate_digest)
            return self._put(actor, 'document-retrieval-evaluation', {
                'schemaVersion':'document-retrieval-evaluation.v0.1',
                'candidateDigest':candidate_digest, 'profileDigest':profile_digest,
                'testSetDigest':test_set_digest, 'execution':'CORE_EXECUTED',
                'report':recomputed})

    def register_answer_runtime_evidence(self, actor, candidate_digest, test_set_digest,
                                         manifest_digest, service_lock_raw,
                                         model_selection_raw, runs, stopped):
        """Correlate original Host archives with immutable Lock and Core receipts.

        This proves which installed Host, model binding, Factory receipts and stopped
        instance produced the archived answers. It deliberately does not accept an
        execution-mode label from the caller.
        """
        actor.require('candidate.validate')
        with self.tx():
            test_object = self._get(actor, test_set_digest, 'document-quality-test-set')
        if test_object['candidateDigest'] != candidate_digest:
            raise Rejected('QUALITY_RUNTIME_BINDING_MISMATCH')
        if not isinstance(service_lock_raw, bytes) or not isinstance(model_selection_raw, bytes):
            raise Rejected('QUALITY_RUNTIME_EVIDENCE_INVALID')
        try:
            service_lock = json.loads(service_lock_raw)
            model_selection = json.loads(model_selection_raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Rejected('QUALITY_RUNTIME_EVIDENCE_INVALID') from None
        lock_digest = hashlib.sha256(service_lock_raw).hexdigest()
        model_digest = hashlib.sha256(model_selection_raw).hexdigest()
        sources = service_lock.get('sources', {})
        if (service_lock.get('files', {}).get('model-selection.json') != model_digest
                or not sources or any(value.get('worktreeDirty') is not False
                                      for value in sources.values() if isinstance(value, dict))):
            raise Rejected('QUALITY_RUNTIME_LOCK_INVALID')
        connections = model_selection.get('connections')
        if (not isinstance(connections, list) or len(connections) != 1
                or not isinstance(model_selection.get('defaultModelRef'), str)):
            raise Rejected('QUALITY_RUNTIME_MODEL_INVALID')
        model = connections[0]
        model_identity = {key:model.get(key) for key in
            ('modelRef', 'configVersion', 'modelName', 'provider')}
        if (model_identity['modelRef'] != model_selection['defaultModelRef']
                or any(not isinstance(value, str) or not value for value in model_identity.values())):
            raise Rejected('QUALITY_RUNTIME_MODEL_INVALID')
        stopped_instance = stopped.get('instance') if isinstance(stopped, dict) else None
        if (not isinstance(stopped_instance, dict) or stopped_instance.get('status') != 'STOPPED'
                or not isinstance(stopped_instance.get('instanceId'), str)):
            raise Rejected('QUALITY_RUNTIME_STOP_INVALID')
        expected_cases = [case['caseId'] for case in test_object['testSet']['cases']]
        by_id = {item.get('caseId'):item for item in runs if isinstance(item, dict)}
        if set(by_id) != set(expected_cases) or len(by_id) != len(runs):
            raise Rejected('QUALITY_RUNTIME_CASE_MISMATCH')
        build_id = instance_id = None
        cases = []
        for case_id in expected_cases:
            item = by_id[case_id]
            archive, rows = item.get('archive'), item.get('historyRows')
            runtime_raw = item.get('runtimeLockRaw')
            if (not isinstance(archive, dict) or not isinstance(rows, list)
                    or not isinstance(runtime_raw, bytes)
                    or hashlib.sha256(runtime_raw).hexdigest() != archive.get('runtimeLockDigest')
                    or archive.get('schemaVersion') != 'finance-knowledge-answer.v0.1'
                    or archive.get('status') != 'COMPLETED'
                    or archive.get('serviceLockDigest') != lock_digest
                    or archive.get('manifest') != manifest_digest):
                raise Rejected('QUALITY_RUNTIME_ARCHIVE_INVALID', case_id)
            build_id = archive['buildId'] if build_id is None else build_id
            instance_id = archive['instanceId'] if instance_id is None else instance_id
            if (archive['buildId'] != build_id or archive['instanceId'] != instance_id
                    or instance_id != stopped_instance['instanceId']):
                raise Rejected('QUALITY_RUNTIME_INSTANCE_MISMATCH', case_id)
            contexts = [row for row in rows if row.get('recordType') == 'model-context']
            returned = [row for row in rows if row.get('schemaVersion') == 'finance-observation.v0.1'
                        and row.get('requestId') == archive['requestId']
                        and row.get('instanceId') == instance_id and row.get('component') == 'model'
                        and row.get('operation') == 'attempt' and row.get('phase') == 'END'
                        and row.get('outcome') == 'RETURNED']
            if (len(contexts) != 1 or contexts[0].get('mode') != 'LIVE'
                    or any(contexts[0].get(key) != model_identity[key]
                           for key in ('modelRef', 'configVersion', 'modelName'))
                    or not returned):
                raise Rejected('QUALITY_RUNTIME_MODEL_EVIDENCE_MISSING', case_id)
            receipts, cited = [], []
            for tool in archive.get('toolResults', []):
                result = tool.get('data', {}).get('result', {})
                receipt = result.get('knowledgeReceipt', {})
                receipt_digest = receipt.get('coreReceiptDigest')
                saved = self._get(actor, receipt_digest, 'document-receipt')
                if (saved.get('manifestDigest') != manifest_digest
                        or saved.get('productId') != archive.get('productId')
                        or saved.get('requestId') != receipt.get('requestId')
                        or saved.get('traceId') != receipt.get('traceId')):
                    raise Rejected('QUALITY_RUNTIME_RECEIPT_MISMATCH', case_id)
                receipts.append(receipt_digest)
                cited.extend(evidence.get('clause') for evidence in result.get('evidence', [])
                             if isinstance(evidence.get('clause'), str))
            if not receipts or not isinstance(archive.get('response'), str):
                raise Rejected('QUALITY_RUNTIME_RECEIPT_MISSING', case_id)
            cases.append({'caseId':case_id, 'answer':archive['response'],
                'answerDigest':text_digest(archive['response']),
                'citedClauses':list(dict.fromkeys(cited)), 'requestId':archive['requestId'],
                'runId':archive['runId'], 'runtimeLockDigest':archive['runtimeLockDigest'],
                'coreReceiptDigests':receipts})
        body = {'schemaVersion':'document-answer-runtime-evidence.v0.1',
            'candidateDigest':candidate_digest, 'testSetDigest':test_set_digest,
            'buildId':build_id, 'instanceId':instance_id,
            'installationLockDigest':lock_digest, 'manifestDigest':manifest_digest,
            'modelIdentity':model_identity, 'cases':cases,
            'stoppedAt':stopped.get('stoppedAt', 'STOP_CONFIRMED_WITHOUT_TIMESTAMP'),
            'verification':'CORE_CORRELATED_HARNESS_ARCHIVE'}
        with self.tx():
            return self._put(actor, 'document-answer-runtime-evidence', body)

    def register_answer_evaluation(self, actor, candidate_digest, profile_digest,
                                   test_set_digest, retrieval_digest,
                                   runtime_evidence_digest):
        actor.require('candidate.validate')
        with self.tx():
            test_object = self._get(actor, test_set_digest, 'document-quality-test-set')
            retrieval = self._get(actor, retrieval_digest, 'document-retrieval-evaluation')
            runtime = self._get(actor, runtime_evidence_digest, 'document-answer-runtime-evidence')
        if (test_object['candidateDigest'] != candidate_digest
                or retrieval['candidateDigest'] != candidate_digest
                or retrieval['profileDigest'] != profile_digest
                or retrieval['testSetDigest'] != test_set_digest
                or runtime['candidateDigest'] != candidate_digest
                or runtime['testSetDigest'] != test_set_digest):
            raise Rejected('QUALITY_ANSWER_BINDING_MISMATCH')
        by_id = {item.get('caseId'): item for item in runtime['cases'] if isinstance(item, dict)}
        if set(by_id) != {case['caseId'] for case in test_object['testSet']['cases']}:
            raise Rejected('QUALITY_ANSWER_CASE_MISMATCH')
        cases, facts, citations, total_facts, total_citations = [], 0, 0, 0, 0
        for gold in test_object['testSet']['cases']:
            item = by_id[gold['caseId']]
            answer, cited = item.get('answer'), item.get('citedClauses')
            if not isinstance(answer, str) or not isinstance(cited, list) or any(not isinstance(v, str) for v in cited):
                raise Rejected('QUALITY_ANSWER_CASE_INVALID', gold['caseId'])
            normalized = normal(answer)
            fact_checks = [{'fact': fact, 'passed': normal(fact) in normalized}
                           for fact in gold['answerFacts']]
            citation_checks = [{'clause': clause, 'passed': clause in cited}
                               for clause in gold['expectedClauses']]
            if not gold['expectedClauses']:
                fact_checks.append({'fact':'SUPPORTED_REFUSAL',
                    'passed': bool(re.search(r'无法|不能|未找到|没有足够|依据不足', answer)) and not cited})
            facts += sum(check['passed'] for check in fact_checks); total_facts += len(fact_checks)
            citations += sum(check['passed'] for check in citation_checks); total_citations += len(citation_checks)
            classification = ('CORRECT' if all(c['passed'] for c in fact_checks + citation_checks)
                              else 'ANSWER_FACT_ERROR' if not all(c['passed'] for c in fact_checks)
                              else 'ANSWER_CITATION_ERROR')
            cases.append({'caseId':gold['caseId'], 'answer':answer, 'answerDigest':text_digest(answer),
                          'citedClauses':cited, 'factChecks':fact_checks,
                          'citationChecks':citation_checks, 'classification':classification})
        metrics = {'factAccuracy': 10000 * facts // total_facts if total_facts else 10000,
                   'citationAccuracy': 10000 * citations // total_citations if total_citations else 10000}
        with self.tx():
            return self._put(actor, 'document-answer-evaluation', {
                'schemaVersion':'document-answer-evaluation.v0.1', 'candidateDigest':candidate_digest,
                'profileDigest':profile_digest, 'testSetDigest':test_set_digest,
                'retrievalEvaluationDigest':retrieval_digest,
                'runtimeEvidenceDigest':runtime_evidence_digest,
                'execution':'CORE_CORRELATED_HARNESS_ARCHIVE',
                'modelIdentity':runtime['modelIdentity'], 'cases':cases, 'metricsBps':metrics})

    def assess_document_quality(self, actor, candidate_digest, profile_digest,
                                test_set_digest, retrieval_digest, answer_digest):
        actor.require('candidate.validate')
        candidate, _, _, index = self._document_parts(actor, candidate_digest)
        with self.tx():
            profile = self._get(actor, profile_digest, 'document-quality-profile')
            test_object = self._get(actor, test_set_digest, 'document-quality-test-set')
            retrieval = self._get(actor, retrieval_digest, 'document-retrieval-evaluation')
            answer = self._get(actor, answer_digest, 'document-answer-evaluation')
        expected = (candidate_digest, profile_digest, test_set_digest)
        if ((retrieval['candidateDigest'], retrieval['profileDigest'], retrieval['testSetDigest']) != expected
                or (answer['candidateDigest'], answer['profileDigest'], answer['testSetDigest']) != expected
                or answer['retrievalEvaluationDigest'] != retrieval_digest
                or test_object['candidateDigest'] != candidate_digest):
            raise Rejected('QUALITY_ADMISSION_BINDING_MISMATCH')
        structure = analyze(index['originalHtml'].encode())
        mapping = map_retrieval_chunks(structure['units'], index['index']['chunks'])
        retrieval_report = {'execution':retrieval['execution'], **retrieval['report']}
        answer_report = {'execution':answer['execution'],
                         'runtimeEvidenceDigest':answer['runtimeEvidenceDigest'],
                         'metricsBps':answer['metricsBps'],
                         'cases':answer['cases']}
        gate = assess_quality_gate(structure['report'], mapping, retrieval_report, answer_report)
        body = {'schemaVersion':'document-quality-admission.v0.1',
                'candidateDigest':candidate_digest, 'sourceDigest':index['sourceDigest'],
                'indexDigest':candidate['indexDigest'], 'profileDigest':profile_digest,
                'testSetDigest':test_set_digest, 'retrievalEvaluationDigest':retrieval_digest,
                'answerEvaluationDigest':answer_digest, 'decision':gate['decision'],
                'checks':gate['checks'], 'gateDigest':gate['digest']}
        with self.tx():
            return self._put(actor, 'document-quality-admission', body)

    def _document_parts(self, actor, candidate_digest):
        candidate = self._get(actor, candidate_digest, 'document-candidate')
        core_candidate, recipe, artifacts, rules = self._parts(actor, candidate['coreCandidateDigest'])
        index = self._get(actor, candidate['indexDigest'], 'document-index')
        source = self._source_access(actor, index['sourceDigest'])
        verify_bridge(index['originalHtml'].encode(), source, index['bridge'], index['bridgeDigest'])
        return candidate, recipe, artifacts, index

    @staticmethod
    def _retrieve(index, question, client, profile=None):
        pinned = index['index']
        try:
            if profile is None:
                rows = client.retrieve(pinned['datasetId'], pinned['documentId'], question)
            elif not hasattr(client, 'retrieve_candidates'):
                raise Rejected('QUALITY_RETRIEVAL_UNSUPPORTED')
            else:
                selected = select_quality(client, pinned['datasetId'], pinned['documentId'],
                                          question, profile['config'])
                rows = [{'id':item['id'], 'text':item['text'],
                         'documentId':item['documentId']} for item in selected]
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
            enrolled = [json.loads(row[0]) for row in self.db.execute(
                "SELECT body FROM objects WHERE tenant=? AND kind='document-quality-test-set'",
                (actor.tenant,)).fetchall()]
            if any(item['candidateDigest'] == candidate_digest for item in enrolled):
                raise Rejected('QUALITY_ADMISSION_REQUIRED')
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

    def publish_quality_document(self, actor, candidate_digest, validation_digest,
                                 approval_digest, quality_admission_digest, revision):
        actor.require('manifest.publish')
        with self.tx():
            candidate, recipe, _, index = self._document_parts(actor, candidate_digest)
            self._document_valid(actor, candidate_digest, validation_digest)
            approval = self._get(actor, approval_digest, 'document-approval')
            admission = self._get(actor, quality_admission_digest, 'document-quality-admission')
            if (approval['candidateDigest'] != candidate_digest
                    or approval['validationDigest'] != validation_digest):
                raise Rejected('DOCUMENT_APPROVAL_MISMATCH')
            if (admission['candidateDigest'] != candidate_digest or admission['decision'] != 'PASS'
                    or admission['sourceDigest'] != index['sourceDigest']
                    or admission['indexDigest'] != candidate['indexDigest']):
                raise Rejected('QUALITY_ADMISSION_FAILED_OR_MISMATCH')
            if self._head(actor, 'recipe', recipe['id'])[1] != digest(recipe):
                raise Rejected('DRAFT_CHANGED_REVALIDATE')
            return self._put(actor, 'document-manifest', {
                'schemaVersion':'document-manifest.v0.1', 'id':candidate['productId'], 'revision':revision,
                'productId':candidate['productId'], 'candidateDigest':candidate_digest,
                'validationDigest':validation_digest, 'approvalDigest':approval_digest,
                'indexDigest':candidate['indexDigest'], 'sourceDigest':index['sourceDigest'],
                'mode':'M2_ISOLATED_DOCUMENT'})

    def _quality_profile_for_candidate(self, actor, candidate_digest):
        admissions = []
        for admission_digest, body in self.db.execute(
                "SELECT digest,body FROM objects WHERE tenant=? AND kind='document-quality-admission'",
                (actor.tenant,)).fetchall():
            admission = json.loads(body)
            if admission['candidateDigest'] == candidate_digest and admission['decision'] == 'PASS':
                admissions.append((admission_digest, admission))
        if not admissions:
            return None
        if len(admissions) != 1:
            raise Rejected('QUALITY_ADMISSION_AMBIGUOUS')
        return self._get(actor, admissions[0][1]['profileDigest'], 'document-quality-profile')

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
            profile = self._quality_profile_for_candidate(actor, manifest['candidateDigest'])
        evidence = self._retrieve(index, question, client, profile)
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
