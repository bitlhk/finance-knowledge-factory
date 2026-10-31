"""Bounded native RAGFlow API adapter; endpoint and identity are server-owned."""
import json
import time
import uuid
from urllib import request, error

from knowledge_core.contracts import Rejected


ENGINE = 'infiniflow/ragflow@sha256:141670c7d25b4421f6378152e583a0fe7e5280ed750c42f7507759192d0dad82'


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
                if type(payload.get('code')) is not int or payload['code']!=0:
                    raise Rejected('RAGFLOW_BUSINESS_ERROR')
                return payload.get('data'),res.headers
        except Rejected:raise
        except (error.HTTPError,error.URLError,TimeoutError,ValueError,AttributeError):
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
        chunks,_=self._http('GET',f'/datasets/{ds}/documents/{doc}/chunks?page_size=100')
        rows=chunks.get('chunks',[])
        if not rows or len(rows)!=chunks.get('total'):raise Rejected('RAGFLOW_CHUNKS_INCOMPLETE')
        self.operations.append({'stage':'INDEX_READY','documentId':doc,'datasetId':ds,'chunkCount':len(rows)})
        return {'datasetId':ds,'documentId':doc,'buildId':build_id,'engineIdentity':ENGINE,
            'embeddingIdentity':'BAAI/bge-small-zh-v1.5:'+self.model_id,
            'chunks':[{'id':c['chunk_id'],'text':c['content_with_weight']} for c in rows]}

    def retrieve(self, dataset, document, question):
        result,_=self._http('POST','/retrieval',{'dataset_ids':[dataset],'document_ids':[document],
            'question':question,'page':1,'page_size':3,'knn_top_k':64,'knn_num_candidates':128,
            'rerank_candidates_count':64,'similarity_threshold':0,'keywords_similarity_weight':0.7,
            'include_knowledge_compilation':False,'highlight':False})
        try:
            rows=result['chunks']
            if not isinstance(rows,list):raise ValueError()
            if any(c['dataset_id']!=dataset for c in rows):raise Rejected('RAGFLOW_DATASET_MISMATCH')
            return [{'id':c['id'],'text':c['content'],'documentId':c['document_id']} for c in rows]
        except Rejected:raise
        except (KeyError,TypeError,ValueError):raise Rejected('RAGFLOW_RESPONSE_INVALID') from None
