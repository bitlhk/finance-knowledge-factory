"""Bounded native RAGFlow API adapter; endpoint and identity are server-owned."""
import json
import hashlib
import time
import threading
import uuid
from urllib import request, error

from knowledge_core.contracts import Rejected


ENGINE = 'infiniflow/ragflow@sha256:141670c7d25b4421f6378152e583a0fe7e5280ed750c42f7507759192d0dad82'
BASELINE_RETRIEVAL = {'pageSize': 3, 'knnTopK': 64, 'knnCandidates': 128,
                      'rerankCandidates': 64, 'similarityThresholdBps': 0,
                      'keywordWeightBps': 7000, 'rerankerId': None}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Ragflow:
    def __init__(self, credentials_path, setup_path, base='http://127.0.0.1:19380/api/v1'):
        if base != 'http://127.0.0.1:19380/api/v1':
            raise Rejected('UNAPPROVED_RAGFLOW_ENDPOINT')
        self.base = base
        self.opener = request.build_opener(NoRedirect())
        self.token = None
        self.operations = []
        self._closed = False
        self._session_check = None
        self._session_reject = None
        credentials = json.loads(credentials_path.read_text())
        data, headers = self._http('POST','/auth/login', {
            'email':'knowledge-m1@example.invalid','password':credentials['password']})
        self.token = headers.get('Authorization')
        if not self.token:
            raise Rejected('RAGFLOW_AUTH_FAILED')
        models = json.loads(setup_path.read_text())['models']
        matching = [m['model_id'] for m in models if m['name']=='BAAI/bge-small-zh-v1.5']
        if len(matching)!=1:
            raise Rejected('EMBEDDING_MODEL_AMBIGUOUS')
        self.model_id = matching[0]

    def _http(self, method, path, data=None, multipart=None):
        if getattr(self, '_closed', False):
            raise Rejected('RAGFLOW_UNAVAILABLE')
        if getattr(self, '_session_check', None) is not None:
            self._session_check()
        headers = {'Accept':'application/json'}
        if self.token:
            headers['Authorization']='Bearer '+self.token
        body = None
        if multipart is not None:
            boundary='kf-m2-'+uuid.uuid4().hex
            headers['Content-Type']='multipart/form-data; boundary='+boundary
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="m2-source.html"\r\nContent-Type: text/html\r\n\r\n'.encode()+multipart+f'\r\n--{boundary}--\r\n'.encode())
        elif data is not None:
            body=json.dumps(data).encode();headers['Content-Type']='application/json'
        try:
            with self.opener.open(request.Request(self.base+path,data=body,headers=headers,method=method),timeout=60) as res:
                raw=res.read(2_000_001)
                if len(raw)>2_000_000:raise Rejected('RAGFLOW_RESPONSE_LIMIT')
                payload=json.loads(raw)
                if getattr(self, '_session_check', None) is not None:
                    self._session_check()
                if type(payload.get('code')) is not int or payload['code']!=0:
                    raise Rejected('RAGFLOW_BUSINESS_ERROR')
                return payload.get('data'),res.headers
        except Rejected:raise
        except error.HTTPError as exc:
            if exc.code == 401 and getattr(self, '_session_reject', None) is not None:
                self._session_reject()
            exc.close()
            raise Rejected('RAGFLOW_UNAVAILABLE') from None
        except (error.URLError,TimeoutError,ValueError,AttributeError):
            raise Rejected('RAGFLOW_UNAVAILABLE') from None

    def ingest(self, raw):
        build_id=uuid.uuid4().hex
        dataset,_=self._http('POST','/datasets', {'name':'m2-'+build_id,
            'embedding_model':self.model_id,'parse_type':1,'parser_id':'laws'})
        ds=dataset['id']
        self.operations.append({'stage':'DATASET_CREATED','buildId':build_id,'datasetId':ds})
        docs,_=self._http('POST',f'/datasets/{ds}/documents',multipart=raw)
        if len(docs)!=1:raise Rejected('RAGFLOW_DOCUMENT_COUNT')
        doc=docs[0]['id']
        self.operations.append({'stage':'DOCUMENT_UPLOADED','documentId':doc,'datasetId':ds})
        self._http('POST',f'/datasets/{ds}/chunks',{'document_ids':[doc]})
        end=time.monotonic()+240
        while time.monotonic()<end:
            state,_=self._http('GET',f'/datasets/{ds}/documents')
            rows=state.get('docs',state.get('documents',[]))
            matching=[r for r in rows if r.get('id')==doc]
            if len(matching)==1 and matching[0].get('progress')==1:break
            if matching and matching[0].get('progress',0)<0:raise Rejected('RAGFLOW_PARSE_FAILED')
            time.sleep(2)
        else:raise Rejected('RAGFLOW_PARSE_TIMEOUT')
        rows = self._ready_chunks(ds, doc)
        self.operations.append({'stage':'INDEX_READY','documentId':doc,'datasetId':ds,'chunkCount':len(rows)})
        return {'datasetId':ds,'documentId':doc,'buildId':build_id,'engineIdentity':ENGINE,
            'embeddingIdentity':'BAAI/bge-small-zh-v1.5:'+self.model_id,
            'chunks':[{'id':c['chunk_id'],'text':c['content_with_weight']} for c in rows]}

    def _ready_chunks(self, dataset, document):
        # Parse completion can precede search-index visibility. Never re-ingest.
        deadline = time.monotonic() + 30
        previous = None
        while True:
            rows, seen, total = [], set(), None
            complete = True
            for page in range(1, 11):
                payload, _ = self._http('GET',
                    f'/datasets/{dataset}/documents/{document}/chunks?page={page}&page_size=100')
                batch = payload.get('chunks') if isinstance(payload, dict) else None
                count = payload.get('total') if isinstance(payload, dict) else None
                if (not isinstance(batch, list) or type(count) is not int or
                        count < 0 or count > 1000 or len(batch) > 100):
                    raise Rejected('RAGFLOW_RESPONSE_INVALID')
                if total is None:
                    total = count
                elif count != total:
                    complete = False
                    break
                for chunk in batch:
                    if (not isinstance(chunk, dict) or not isinstance(chunk.get('chunk_id'), str)
                            or not chunk['chunk_id'] or not isinstance(chunk.get('content_with_weight'), str)
                            or not chunk['content_with_weight'].strip()):
                        raise Rejected('RAGFLOW_RESPONSE_INVALID')
                    if chunk['chunk_id'] in seen:
                        raise Rejected('RAGFLOW_DUPLICATE_CHUNK')
                    seen.add(chunk['chunk_id'])
                    rows.append(chunk)
                if len(rows) > total:
                    raise Rejected('RAGFLOW_RESPONSE_INVALID')
                if not batch or len(rows) == total:
                    break
            complete = complete and bool(rows) and len(rows) == total
            fingerprint = hashlib.sha256(json.dumps(sorted(
                (r['chunk_id'], r['content_with_weight']) for r in rows),
                ensure_ascii=False).encode()).hexdigest() if complete else None
            self.operations.append({'stage': 'INDEX_VISIBILITY_CHECK', 'datasetId': dataset,
                'documentId': document, 'expectedCount': total, 'receivedCount': len(rows),
                'complete': complete, 'stable': complete and fingerprint == previous})
            if complete and fingerprint == previous:
                return rows
            if time.monotonic() >= deadline:
                raise Rejected('RAGFLOW_CHUNKS_INCOMPLETE')
            previous = fingerprint
            time.sleep(2)

    def retrieve(self, dataset, document, question):
        rows = self.retrieve_candidates(dataset, document, question, BASELINE_RETRIEVAL)
        return [{'id':c['id'],'text':c['text'],'documentId':c['documentId']} for c in rows]

    def retrieve_candidates(self, dataset, document, question, profile):
        required = {'pageSize', 'knnTopK', 'knnCandidates', 'rerankCandidates',
                    'similarityThresholdBps', 'keywordWeightBps', 'rerankerId'}
        if (not isinstance(profile, dict) or set(profile) != required
                or any(type(profile[key]) is not int for key in required - {'rerankerId'})
                or not 1 <= profile['pageSize'] <= 64
                or not 1 <= profile['knnTopK'] <= 1024
                or not 1 <= profile['knnCandidates'] <= 2048
                or not 1 <= profile['rerankCandidates'] <= 1024
                or not 0 <= profile['similarityThresholdBps'] <= 10000
                or not 0 <= profile['keywordWeightBps'] <= 10000
                or profile['rerankerId'] is not None and not isinstance(profile['rerankerId'], str)):
            raise Rejected('RETRIEVAL_PROFILE_INVALID')
        request_body = {'dataset_ids':[dataset], 'document_ids':[document], 'question':question,
            'page':1, 'page_size':profile['pageSize'], 'knn_top_k':profile['knnTopK'],
            'knn_num_candidates':profile['knnCandidates'],
            'rerank_candidates_count':profile['rerankCandidates'],
            'similarity_threshold':profile['similarityThresholdBps'] / 10000,
            'keywords_similarity_weight':profile['keywordWeightBps'] / 10000,
            'include_knowledge_compilation':False, 'highlight':False}
        if profile['rerankerId'] is not None:
            request_body['rerank_id'] = profile['rerankerId']
        result,_=self._http('POST','/retrieval',request_body)
        try:
            rows=result['chunks']
            if not isinstance(rows,list):raise ValueError()
            if any(c['dataset_id']!=dataset for c in rows):raise Rejected('RAGFLOW_DATASET_MISMATCH')
            output = []
            for rank, candidate in enumerate(rows, 1):
                scores = []
                for key in ('similarity', 'term_similarity', 'vector_similarity'):
                    value = candidate.get(key)
                    if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                              or not 0 <= value <= 1):
                        raise ValueError()
                    scores.append(None if value is None else round(value * 10000))
                output.append({'id':candidate['id'], 'text':candidate['content'],
                    'documentId':candidate['document_id'], 'rank':rank,
                    'scoreBps':scores[0], 'termScoreBps':scores[1], 'vectorScoreBps':scores[2]})
            return output
        except Rejected:raise
        except (KeyError,TypeError,ValueError):raise Rejected('RAGFLOW_RESPONSE_INVALID') from None


class _SessionQueryClient(Ragflow):
    def close(self):
        self._closed = True
        self.token = None

    def ingest(self, raw):
        raise Rejected('RAGFLOW_UNAVAILABLE')


class RagflowQuerySession:
    """One lazy upstream login per service, not a cache of Host/Core authority.

    Each request gets its own opener. A rejected session is terminal for this
    process: no automatic login refresh or query retry, including after failures.
    """
    def __init__(self, credentials_path, setup_path, *, client_type=Ragflow):
        self.credentials_path, self.setup_path = credentials_path, setup_path
        self.client_type = client_type
        self._lock = threading.Lock()
        self._client = None
        self._closed = False
        self._failure = None
        self.login_attempts = 0

    def _check(self):
        with self._lock:
            if self._closed or self._failure is not None:
                raise Rejected(self._failure or 'RAGFLOW_UNAVAILABLE')

    def _reject(self):
        with self._lock:
            self._failure = 'RAGFLOW_UNAVAILABLE'
            if self._client is not None:
                self._client.token = None

    def __call__(self):
        with self._lock:
            if self._closed or self._failure is not None:
                raise Rejected(self._failure or 'RAGFLOW_UNAVAILABLE')
            if self._client is None:
                self.login_attempts += 1
                try:
                    self._client = self.client_type(self.credentials_path, self.setup_path)
                except Exception as exc:
                    self._failure = exc.code if isinstance(exc, Rejected) else 'RAGFLOW_UNAVAILABLE'
                    raise Rejected(self._failure) from None
            # Transport state and close() belong to this query, not another thread.
            client = object.__new__(_SessionQueryClient)
            client.base, client.model_id = self._client.base, self._client.model_id
            client.token = self._client.token
            client.opener = request.build_opener(NoRedirect())
            client.operations = []
            client._closed = False
            client._session_check, client._session_reject = self._check, self._reject
            return client

    def close(self):
        with self._lock:
            self._closed = True
            if self._client is not None:
                self._client.token = None
