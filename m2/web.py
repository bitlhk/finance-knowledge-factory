"""Single-operator loopback UI adapter; Core is the only release authority.

Fixed synthetic identities and business context are server owned. This is not an
Internet-ready IAM adapter. Job files store provenance, never publication flags.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
from http.server import ThreadingHTTPServer

from knowledge_core.contracts import Rejected, digest
from knowledge_core.documents import DocumentCore
from m2.acceptance import AUTHOR, READER, CONTEXT, SCOPE
from m2.pipeline import produce, parse
from m2.ragflow import Ragflow
from web_production.engine import Production, now
from web_production.server import handler


class DocumentProduction(Production):
    m2 = True

    def __init__(self, state, client_factory):
        self.database=Path(state)/'core.sqlite'
        self.client_factory=client_factory
        super().__init__(state, caller=lambda _: (_ for _ in ()).throw(Rejected('DOCUMENT_ONLY_REQUIRED')))
        self.core().close()

    def core(self):
        return DocumentCore(self.database)

    def recipe_metadata(self, data):
        return {'documentPipeline':'native-ragflow+verified-html-anchors.v0.1',
                'delivery':'CORE_ISOLATED_DOCUMENT_CANDIDATE','trustedContext':CONTEXT.facts(),
                'approvalAuthority':'ISOLATED_TEST_ONLY'}

    def submit(self, data):
        if data.get('rules') is not False or data.get('clauses') or data.get('modelConsent') is not False:
            raise Rejected('DOCUMENT_ONLY_REQUIRED')
        if not data.get('tests'):
            raise Rejected('RETRIEVAL_GOLD_REQUIRED')
        with self.lock:
            if len(self.jobs)>=20 and not any(j['requestId']==data.get('requestId') for j in self.jobs.values()):
                raise Rejected('ISOLATED_RUN_LIMIT')
            return super().submit(data)

    def _grant_product(self, core, product):
        revision,sha=core._head(AUTHOR,'policy','current')
        grants=core._get(AUTHOR,sha,'active-policy')['grants'] if sha else []
        for principal in (AUTHOR.principal,READER.principal):
            grants += [{'principal':principal,'resource':'product:'+product,'actions':['consume','history']},
                       {'principal':principal,'resource':'source:'+product+'-source','actions':['source_read']}]
        core.set_policy(AUTHOR,{'schemaVersion':'active-policy.v0.1','revision':revision+1,'grants':grants},revision)

    def run(self, run_id):
        job=self.jobs[run_id]
        core=self.core()
        client=None
        try:
            with self.lock:
                job.update(status='RUNNING',startedAt=now())
                job['implementation'].update({str(p.relative_to(Path(__file__).parents[1])):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in Path(__file__).parent.glob('*.py')})
                self.save(job)
                self._grant_product(core,run_id)
            raw=self.sources[job['sourceId']]['html'].encode()
            self.stage(job,'parse','RUNNING')
            clauses=parse(raw)
            self.stage(job,'parse','COMPLETED',clauseCount=len(clauses))
            self.stage(job,'documents','RUNNING',executor='RAGFLOW_NATIVE_HTTP')
            client=self.client_factory()
            objects=produce(core,AUTHOR,run_id,1,raw,SCOPE,job['recipe']['tests'],[READER.principal],client)
            index=core._get(AUTHOR,objects['indexDigest'],'document-index')
            with self.lock:
                job['coreObjects']=objects
                job['nativeOperations']=copy.deepcopy(client.operations)
                self.save(job)
            self.stage(job,'documents','COMPLETED',datasetId=index['index']['datasetId'],
                       documentId=index['index']['documentId'],chunkCount=len(index['index']['chunks']))
            self.stage(job,'rules','NOT_SELECTED')
            self.stage(job,'validation','RUNNING')
            validation=core.validate_document(AUTHOR,objects['candidateDigest'],client)
            result=core._get(AUTHOR,validation,'document-validation')
            artifact={'schemaVersion':'m2-document-display.v0.1','documentClauses':clauses,'rules':[],
                'candidateDigest':objects['candidateDigest'],'indexDigest':objects['indexDigest'],
                'source':core._get(AUTHOR,objects['sourceDigest'],'source-revision'),'bridge':index['bridge'],
                'validation':{'retrievalTests':result['results'],'coreValidationDigest':validation,
                              'passed':result['passed'],'scope':'USER_SUPPLIED_DOCUMENT_TESTS_ONLY'},
                'publicationAllowed':False,'status':'CORE_CANDIDATE'}
            self.stage(job,'validation','COMPLETED' if result['passed'] else 'FAILED',validationDigest=validation)
            with self.lock:
                job.update(artifact=artifact,artifactDigest=digest(artifact),
                           status='COMPLETED' if result['passed'] else 'PARTIAL',finishedAt=now())
                self.save(job)
        except Exception as exc:
            with self.lock:
                job.update(status='FAILED',error=getattr(exc,'code',type(exc).__name__),finishedAt=now(),
                           nativeOperations=copy.deepcopy(client.operations) if client else [])
                self.save(job)
        finally:
            core.close()

    @staticmethod
    def _latest(core, kind, candidate):
        rows=core.db.execute('SELECT digest FROM objects WHERE tenant=? AND kind=? AND json_extract(body,\'$.candidateDigest\')=? ORDER BY rowid DESC LIMIT 1',
                            (AUTHOR.tenant,kind,candidate)).fetchall()
        return rows[0][0] if rows else None

    def _release(self, core, job):
        objects=job.get('coreObjects')
        if not objects:return {'state':'NO_CANDIDATE'}
        candidate=objects['candidateDigest']
        core._document_parts(AUTHOR,candidate)
        val=self._latest(core,'document-validation',candidate)
        approval=self._latest(core,'document-approval',candidate)
        binding_sha=core._head(AUTHOR,'document-binding',job['id'])[1]
        binding=core._get(AUTHOR,binding_sha,'document-binding') if binding_sha else None
        manifest=binding['manifestDigest'] if binding else None
        published=bool(manifest)
        if manifest:
            frozen=core._get(AUTHOR,manifest,'document-manifest')
            if frozen['candidateDigest']!=candidate:raise Rejected('CANDIDATE_MISMATCH')
            val,approval=frozen['validationDigest'],frozen['approvalDigest']
        elif approval and core._get(AUTHOR,approval,'document-approval')['validationDigest']!=val:
            approval=None
        valid=core._get(AUTHOR,val,'document-validation')['passed'] if val else False
        return {'state':'ISOLATED_PUBLISHED' if published else 'APPROVED' if approval else 'VALIDATED' if valid else 'REVIEW_REQUIRED',
                'candidateDigest':candidate,'validationDigest':val,'approvalDigest':approval,
                'approvalReason':core._get(AUTHOR,approval,'document-approval')['reason'] if approval else None,
                'manifestDigest':manifest,'bindingDigest':binding_sha,'productId':job['id'],
                'authority':'ISOLATED_TEST_ONLY','scope':SCOPE,'businessContext':CONTEXT.facts()}

    def get(self, run_id):
        job=super().get(run_id)
        core=self.core()
        try:
            job['release']=self._release(core,job)
            rows=core.db.execute("SELECT digest FROM objects WHERE tenant=? AND kind='document-receipt' AND json_extract(body,'$.productId')=? ORDER BY rowid",(READER.tenant,run_id))
            job['consumptionReceipts']=[self._receipt(core.replay_document(READER,row[0]),run_id) for row in rows.fetchall()]
            return job
        finally:core.close()

    @staticmethod
    def _receipt(receipt,run_id):
        return {'id':'query-'+receipt['receiptDigest'],'runId':run_id,'createdAt':receipt['createdAt'],
                'query':receipt['question'],'hits':[{'clause':e['clause'],'text':e['quote'],'anchors':e['anchors']}
                    for e in receipt['result']['evidence']], 'method':'RAGFLOW_PINNED_MANIFEST',
                'generatedAnswer':False,'receipt':receipt,'publicationAllowed':False}

    def snapshot(self):
        state=super().snapshot()
        releases=[]
        core=self.core()
        try:
            for job in list(self.jobs.values()):
                release=self._release(core,job)
                if release['state']=='ISOLATED_PUBLISHED':
                    releases.append({'runId':job['id'],'title':job['title'],'sourceId':job['sourceId'],**release})
        finally:core.close()
        return {**state,'m2':True,'modelReady':False,'engineReady':False,'mode':'M2_ISOLATED_DOCUMENT',
                'isolatedReleases':releases,'isolatedApprovalAllowed':True,'parameters':{},'recipe':'m2-document-core'}

    def release_action(self, path, data):
        if path not in {'/api/document-approve','/api/document-publish'}:raise Rejected('RELEASE_CONTRACT_INVALID')
        if set(data)!={'runId','candidateDigest','reason'} or not isinstance(data['reason'],str) or not 1<=len(data['reason'].strip())<=1000:
            raise Rejected('RELEASE_CONTRACT_INVALID')
        with self.lock:
            job=super().get(data['runId'])
            if job['status']!='COMPLETED':raise Rejected('CANDIDATE_NOT_VALIDATED')
            core=self.core()
            try:
                release=self._release(core,job)
                if release.get('candidateDigest')!=data['candidateDigest']:raise Rejected('CANDIDATE_MISMATCH')
                if path=='/api/document-approve':
                    if release['state']!='ISOLATED_PUBLISHED':
                        core.approve_document(AUTHOR,data['candidateDigest'],release['validationDigest'],data['reason'])
                else:
                    if not release.get('approvalDigest'):raise Rejected('DOCUMENT_APPROVAL_REQUIRED')
                    if data['reason']!=release['approvalReason']:raise Rejected('APPROVAL_REASON_MISMATCH')
                    if release['state']!='ISOLATED_PUBLISHED':
                        try:core._source_current(AUTHOR,job['coreObjects']['sourceDigest'],CONTEXT.business_date)
                        except Rejected as exc:
                            if exc.code!='SOURCE_NOT_EFFECTIVE':raise
                            core.activate_source(AUTHOR,job['coreObjects']['sourceDigest'],CONTEXT.business_date)
                        manifest=core.publish_document(AUTHOR,data['candidateDigest'],release['validationDigest'],release['approvalDigest'],1)
                        core.bind_document(AUTHOR,manifest,0)
                return self._release(core,job)
            finally:core.close()

    def search(self, run_id, query):
        job=self.get(run_id)
        if job['release']['state']!='ISOLATED_PUBLISHED':raise Rejected('DOCUMENT_NOT_PUBLISHED')
        core=self.core()
        try:
            # Client creation/login is intentionally lazy, after Core's pre-retrieval authorization.
            factory=self.client_factory
            class Retrieval:
                def retrieve(self,*args):return factory().retrieve(*args)
            import uuid
            receipt=core.query_document(READER,run_id,job['release']['manifestDigest'],CONTEXT,query,
                'request-'+uuid.uuid4().hex,'trace-'+uuid.uuid4().hex,Retrieval())
            return self._receipt(receipt,run_id)
        finally:core.close()

    def rule_test(self,*args):raise Rejected('DOCUMENT_ONLY_REQUIRED')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--state',type=Path,required=True)
    ap.add_argument('--private-config',type=Path,required=True)
    ap.add_argument('--port',type=int,default=61353)
    args=ap.parse_args()
    args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (args.state/'.server.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        service=DocumentProduction(args.state,lambda:Ragflow(args.private_config/'local-credentials.json',args.private_config/'http-setup.json'))
        http=ThreadingHTTPServer(('127.0.0.1',args.port),handler(service))
        (args.state/'server.pid').write_text(str(os.getpid()))
        print(f'M2 isolated document preview http://127.0.0.1:{args.port}/',flush=True)
        try:http.serve_forever()
        finally:http.server_close();service.close()


if __name__=='__main__':main()
