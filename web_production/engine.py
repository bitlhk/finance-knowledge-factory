"""New production runs; no historical model response or published M0 writes."""
import copy
import hashlib
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from lxml import html
from knowledge_core.contracts import Rejected
from knowledge_core.evidence.json_digest import evidence_digest as digest
from knowledge_core.evidence.html_evidence import locate, verify
from knowledge_core.evidence.anchor_bridge import build, bind_rule_evidence, verify_bridge

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'evidence/m1-round3/sources/regulation.html'
SAMPLE_SHA = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
PARAMETERS = dict(model='deepseek-v4-flash', temperature=0.1, top_p=1,
                  max_tokens=4096, thinking={'type': 'disabled'}, stream=False)
TERMINAL = {'COMPLETED', 'PARTIAL', 'FAILED', 'INTERRUPTED'}


def now():
    return datetime.now(timezone.utc).isoformat()


def persist(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def parse(raw):
    if not raw or len(raw) > 1_000_000:
        raise Rejected('HTML_SIZE_LIMIT')
    text = raw.decode('utf-8', errors='strict')
    if '<html' not in text.lower() and not re.search(r'<(?:p|div|article)\b', text, re.I):
        raise Rejected('HTML_REQUIRED')
    tree = html.fromstring(text, parser=html.HTMLParser(no_network=True))
    texts = tree.xpath('//text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::noscript)]')
    chunks = locate(raw, list(map(str, texts)))
    if not chunks or len(chunks) > 300 or not all(verify(raw, c) for c in chunks):
        raise Rejected('NO_VERIFIABLE_NUMBERED_CLAUSES')
    if len({c['clause'] for c in chunks}) != len(chunks):
        raise Rejected('DUPLICATE_CLAUSE_NUMBER')
    return chunks


class Production:
    def recipe_metadata(self, data):
        return {}

    def __init__(self, state, caller=None, executor=None):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.pool = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix='knowledge-production')
        self.caller = caller
        self.sources, self.jobs = {}, {}
        for path in self.state.glob('source-*.json'):
            obj = json.loads(path.read_text())
            raw = obj['html'].encode()
            if hashlib.sha256(raw).hexdigest() != obj['id']:
                raise Rejected('SOURCE_STORAGE_CHANGED')
            self.sources[obj['id']] = obj
        for path in self.state.glob('run-*.json'):
            job = json.loads(path.read_text())
            if job.get('status') not in TERMINAL:
                job.update(status='INTERRUPTED', error='SERVER_RESTART_NO_AUTOMATIC_RETRY', finishedAt=now())
                persist(path, job)
            self.jobs[job['id']] = job

    def close(self):
        self.pool.shutdown(wait=True)

    def save(self, job):
        persist(self.state / (job['id'] + '.json'), job)

    def source(self, title, text):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or not isinstance(text, str):
            raise Rejected('INVALID_SOURCE')
        raw = text.encode()
        chunks = parse(raw)
        sha = hashlib.sha256(raw).hexdigest()
        with self.lock:
            if sha not in self.sources:
                if len(self.sources) >= 40:
                    raise Rejected('PREVIEW_SOURCE_LIMIT')
                obj = dict(id=sha, title=title.strip(), importedAt=now(), html=text,
                           clauses=chunks, parser='native-html-dom-v0.1', authoritative=False)
                persist(self.state / ('source-' + sha + '.json'), obj)
                self.sources[sha] = obj
            return self.public_source(self.sources[sha])

    @staticmethod
    def public_source(src):
        return {k: v for k, v in src.items() if k != 'html'}

    def get(self, run_id):
        with self.lock:
            if run_id not in self.jobs:
                raise Rejected('RUN_NOT_FOUND')
            job = copy.deepcopy(self.jobs[run_id])
        if job.get('artifactDigest') and digest(job['artifact']) != job['artifactDigest']:
            raise Rejected('CANDIDATE_DIGEST_MISMATCH')
        receipts = []
        for pattern in ('query-*.json', 'test-*.json'):
            for path in self.state.glob(pattern):
                receipt = json.loads(path.read_text())
                if receipt.get('runId') == run_id:
                    if receipt.get('artifactDigest') != job.get('artifactDigest'):
                        raise Rejected('RECEIPT_CANDIDATE_MISMATCH')
                    receipts.append(receipt)
        job['consumptionReceipts'] = sorted(receipts, key=lambda r: r['createdAt'])
        return job

    def snapshot(self):
        with self.lock:
            return {'sources': [self.public_source(s) for s in self.sources.values()],
                    'runs': [{k: j.get(k) for k in ('id', 'sourceId', 'title', 'status', 'createdAt', 'finishedAt')}
                             for j in reversed(list(self.jobs.values()))],
                    'modelReady': False,
                    'engineReady': False,
                    'publicationAllowed': False, 'mode': 'ISOLATED_CANDIDATE_PRODUCTION',
                    'parameters': PARAMETERS, 'recipe': 'semantic-before-lowering', 'sampleDigest': SAMPLE_SHA}

    def submit(self, data):
        if set(data) != {'requestId', 'sourceId', 'rules', 'clauses', 'tests', 'modelConsent'}:
            raise Rejected('RUN_CONTRACT_INVALID')
        if not isinstance(data['requestId'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', data['requestId']):
            raise Rejected('INVALID_REQUEST_ID')
        if type(data['rules']) is not bool or type(data['modelConsent']) is not bool:
            raise Rejected('INVALID_BOOLEAN')
        if data['rules']:
            raise Rejected('RULE_EXPERIMENT_ISOLATED')
        if not isinstance(data['clauses'], list) or len(data['clauses']) > 2 or any(not isinstance(c, str) for c in data['clauses']):
            raise Rejected('RULE_SELECTION_LIMIT_TWO')
        if len(set(data['clauses'])) != len(data['clauses']):
            raise Rejected('DUPLICATE_SELECTION')
        tests = data['tests']
        if not isinstance(tests, list) or len(tests) > 30:
            raise Rejected('TEST_SET_LIMIT')
        for test in tests:
            if not isinstance(test, dict) or set(test) != {'question', 'expectedClause'} or any(
                    not isinstance(v, str) or not 1 <= len(v) <= 300 for v in test.values()):
                raise Rejected('TEST_SET_INVALID')
        frozen_digest = digest(data)
        with self.lock:
            for job in self.jobs.values():
                if job['requestId'] == data['requestId']:
                    if job['submissionDigest'] != frozen_digest:
                        raise Rejected('IDEMPOTENCY_CONFLICT')
                    return self.get(job['id'])
            if any(j['status'] not in TERMINAL for j in self.jobs.values()):
                raise Rejected('PRODUCTION_BUSY')
            if len(self.jobs) >= 40:
                raise Rejected('PREVIEW_RUN_LIMIT')
            src = self.sources.get(data['sourceId'])
            if src is None:
                raise Rejected('SOURCE_NOT_FOUND')
            available = {c['clause'] for c in src['clauses']}
            if set(data['clauses']) - available or any(t['expectedClause'] not in available for t in tests):
                raise Rejected('CLAUSE_NOT_IN_SOURCE')
            if data['rules'] and (not data['clauses'] or not data['modelConsent']):
                raise Rejected('MODEL_SCOPE_AND_CONSENT_REQUIRED')
            if not data['rules'] and data['clauses']:
                raise Rejected('DOCUMENT_ONLY_HAS_RULE_SELECTION')
            recipe = {'version': 'production-recipe.v0.2', 'sourceId': src['id'],
                      'documentPipeline': 'native-html-dom+character-bigram-search.v0.1',
                      'rulePipeline': None,
                      'loweringConfig': None,
                      'selectedClauses': data['clauses'], 'tests': tests,
                      'parameters': PARAMETERS if data['rules'] else None,
                      'delivery': 'LOCAL_UNPUBLISHED_CANDIDATE', 'publicationAllowed': False}
            recipe.update(self.recipe_metadata(data))
            job = dict(id='run-' + uuid.uuid4().hex, requestId=data['requestId'],
                       submissionDigest=frozen_digest, sourceId=src['id'], title=src['title'],
                       recipe=recipe, recipeDigest=digest(recipe), createdAt=now(), status='QUEUED',
                       publicationAllowed=False, stages=[], attempts=[], cost=None,
                       artifact=None, artifactDigest=None)
            job['implementation'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for pattern in ('web_production/*.py', 'knowledge_core/evidence/*.py', 'knowledge_core/*.py')
                for p in sorted(ROOT.glob(pattern))}
            self.jobs[job['id']] = job
            self.save(job)
            self.pool.submit(self.run, job['id'])
            return copy.deepcopy(job)

    def stage(self, job, name, state, **detail):
        with self.lock:
            job['stages'].append(dict(name=name, status=state, time=now(), **detail))
            self.save(job)

    def run(self, run_id):
        job = self.jobs[run_id]
        try:
            with self.lock:
                job.update(status='RUNNING', startedAt=now())
                self.save(job)
            if job['recipe']['selectedClauses'] or job['recipe']['rulePipeline']:
                raise Rejected('RULE_EXPERIMENT_ISOLATED')
            raw = self.sources[job['sourceId']]['html'].encode()
            self.stage(job, 'parse', 'RUNNING')
            chunks = parse(raw)
            source, bridge = build(raw, chunks, 'source-' + job['sourceId'][:16])
            verify_bridge(raw, source, bridge, digest(bridge))
            self.stage(job, 'parse', 'COMPLETED', clauseCount=len(chunks), anchorCount=len(bridge['mappings']))
            artifact = dict(schemaVersion='production-candidate.v0.2', runId=run_id,
                            sourceDigest=job['sourceId'], recipeDigest=job['recipeDigest'],
                            documentClauses=chunks, source=source, bridge=bridge, rules=[],
                            publicationAllowed=False, status='UNAPPROVED_CANDIDATE')
            with self.lock:
                job['artifact'] = artifact
            self.stage(job, 'documents', 'COMPLETED', count=len(chunks), faqGenerated=False)
            selected = job['recipe']['selectedClauses']
            self.stage(job, 'rules', 'RUNNING' if selected else 'NOT_SELECTED', selected=selected)
            failures = sum(a['status'] == 'FAILED' for a in job['attempts'])
            if selected:
                self.stage(job, 'rules', 'PARTIAL' if failures else 'COMPLETED', failures=failures,
                           unprocessedClauseCount=len(chunks) - len(selected))
            self.stage(job, 'validation', 'RUNNING')
            checks = []
            for test in job['recipe']['tests']:
                hits = self.search_artifact(artifact, test['question'])
                checks.append({**test, 'retrievedClauses': [h['clause'] for h in hits],
                               'passed': test['expectedClause'] in {h['clause'] for h in hits}})
            artifact['validation'] = dict(anchorChecks='PASSED', retrievalTests=checks,
                retrievalTestOrigin='USER_SUPPLIED_NOT_INDEPENDENT_GOLD', ruleSemanticQuality='NOT_ACCEPTED',
                ruleExecution='NOT_RUN_NO_FACT_INPUTS', engineCalls=0,
                overall='REVIEW_REQUIRED' if selected else 'EVIDENCE_CANDIDATE_ONLY')
            self.stage(job, 'validation', 'COMPLETED', semanticQuality='NOT_ACCEPTED', engineCalls=0)
            with self.lock:
                job.update(status='PARTIAL' if failures else 'COMPLETED', finishedAt=now(),
                           artifactDigest=digest(artifact))
                self.save(job)
        except Exception as exc:
            with self.lock:
                job.update(status='FAILED', error=getattr(exc, 'code', type(exc).__name__), finishedAt=now())
                self.save(job)

    @staticmethod
    def search_artifact(artifact, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300:
            raise Rejected('QUERY_INVALID')
        clean = lambda s: re.sub(r'\s+', '', s)
        q = clean(query)
        grams = {q[i:i+2] for i in range(len(q) - 1)} or {q}
        ranked = []
        for chunk in artifact['documentClauses']:
            text = clean(chunk['text'])
            score = sum(g in text for g in grams) / len(grams)
            if chunk['clause'] in q:
                score += 2
            if score > 0:
                ranked.append({**chunk, 'score': round(score, 4)})
        return sorted(ranked, key=lambda c: c['score'], reverse=True)[:3]

    def search(self, run_id, query):
        job = self.get(run_id)
        if not job.get('artifactDigest'):
            raise Rejected('CANDIDATE_NOT_SEALED')
        result = dict(id='query-' + uuid.uuid4().hex, runId=run_id, artifactDigest=job['artifactDigest'],
                      createdAt=now(), query=query, hits=self.search_artifact(job['artifact'], query),
                      method='character-bigram-search.v0.1', generatedAnswer=False, publicationAllowed=False)
        persist(self.state / (result['id'] + '.json'), result)
        return result

    def rule_test(self, *args):
        raise Rejected('RULE_EXPERIMENT_ISOLATED')
