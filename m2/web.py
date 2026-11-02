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
from m2.synthetic_context import AUTHOR, READER, REVIEWER, CONTEXT, SCOPE
from m2.pipeline import produce, parse
from m2.ragflow import Ragflow
from web_production.engine import Production, now
from web_production.server import handler


class DocumentProduction(Production):
    m2 = True

    def __init__(self, state, client_factory, evaluation_launcher=None):
        self.database=Path(state)/'core.sqlite'
        self.client_factory=client_factory
        self.evaluation_launcher=evaluation_launcher
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
        for principal in (AUTHOR.principal,READER.principal,REVIEWER.principal):
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

    @staticmethod
    def _quality_report(core, candidate, admission_digest):
        admission=core._get(AUTHOR,admission_digest,'document-quality-admission')
        if admission['candidateDigest']!=candidate:
            raise Rejected('QUALITY_ADMISSION_FAILED_OR_MISMATCH')
        answer=core._get(AUTHOR,admission['answerEvaluationDigest'],'document-answer-evaluation')
        runtime_kind=core.db.execute('SELECT kind FROM objects WHERE tenant=? AND digest=?',
            (AUTHOR.tenant,answer['runtimeEvidenceDigest'])).fetchone()
        if not runtime_kind or runtime_kind[0] not in {
                'document-answer-runtime-evidence','document-factory-evaluation-runtime-evidence'}:
            raise Rejected('QUALITY_RUNTIME_EVIDENCE_INVALID')
        runtime=core._get(AUTHOR,answer['runtimeEvidenceDigest'],runtime_kind[0])
        retrieval=core._get(AUTHOR,admission['retrievalEvaluationDigest'],
                            'document-retrieval-evaluation')
        return {'decision':admission['decision'],'admissionDigest':admission_digest,
            'profileDigest':admission['profileDigest'],'testSetDigest':admission['testSetDigest'],
            'retrievalEvaluationDigest':admission['retrievalEvaluationDigest'],
            'answerEvaluationDigest':admission['answerEvaluationDigest'],
            'runtimeEvidenceDigest':answer['runtimeEvidenceDigest'],
            'evidenceAuthority':answer.get('evidenceAuthority','HARNESS_ARCHIVE'),
            'modelIdentity':answer['modelIdentity'],'metricsBps':answer['metricsBps'],
            'checks':admission['checks'],'retrieval':retrieval['report'],
            'cases':answer['cases'],'runtimeCases':runtime['cases']}

    def _evaluation(self, core, job):
        saved=job.get('qualityEvaluation')
        if not saved:
            return {'state':'NOT_STARTED'}
        result={key:value for key,value in saved.items() if key!='digests'}
        result['state']=result.pop('status')
        if saved.get('status')=='COMPLETED':
            digests=saved.get('digests') or {}
            if set(digests)!={'runtimeEvidenceDigest','answerEvaluationDigest',
                              'qualityAdmissionDigest'}:
                raise Rejected('QUALITY_EVALUATION_RESULT_INVALID')
            report=self._quality_report(core,job['coreObjects']['candidateDigest'],
                                        digests['qualityAdmissionDigest'])
            if (report['runtimeEvidenceDigest']!=digests['runtimeEvidenceDigest']
                    or report['answerEvaluationDigest']!=digests['answerEvaluationDigest']):
                raise Rejected('QUALITY_EVALUATION_RESULT_INVALID')
            result['report']=report
        return result

    def _run_evaluation(self, run_id, evaluation_id):
        try:
            with self.lock:
                job=self.jobs[run_id]
                if job.get('qualityEvaluation',{}).get('id')!=evaluation_id:
                    return
                job['qualityEvaluation'].update(status='RUNNING',startedAt=now())
                self.save(job)
            result=self.evaluation_launcher.evaluate(
                database=self.database,job=copy.deepcopy(job),
                client_factory=self.client_factory)
            if not isinstance(result,dict) or set(result)!={
                    'runtimeEvidenceDigest','answerEvaluationDigest','qualityAdmissionDigest'}:
                raise Rejected('QUALITY_EVALUATION_RESULT_INVALID')
            core=self.core()
            try:
                report=self._quality_report(core,job['coreObjects']['candidateDigest'],
                                            result['qualityAdmissionDigest'])
                if (report['runtimeEvidenceDigest']!=result['runtimeEvidenceDigest']
                        or report['answerEvaluationDigest']!=result['answerEvaluationDigest']):
                    raise Rejected('QUALITY_EVALUATION_RESULT_INVALID')
            finally:core.close()
            with self.lock:
                current=self.jobs[run_id]['qualityEvaluation']
                if current['id']==evaluation_id:
                    current.update(status='COMPLETED',finishedAt=now(),digests=result)
                    self.save(self.jobs[run_id])
        except Exception as exc:
            with self.lock:
                current=self.jobs[run_id].get('qualityEvaluation',{})
                if current.get('id')==evaluation_id:
                    current.update(status='FAILED',finishedAt=now(),
                                   error=getattr(exc,'code',type(exc).__name__))
                    self.save(self.jobs[run_id])

    def start_evaluation(self, data):
        if set(data)!={'runId','candidateDigest'}:
            raise Rejected('QUALITY_EVALUATION_REQUEST_INVALID')
        if self.evaluation_launcher is None:
            raise Rejected('EVALUATION_SERVICE_NOT_READY')
        with self.lock:
            job=self.jobs.get(data['runId'])
            if not job:
                raise Rejected('RUN_NOT_FOUND')
            candidate=job.get('coreObjects',{}).get('candidateDigest')
            if candidate!=data['candidateDigest']:
                raise Rejected('CANDIDATE_MISMATCH')
            if job['status']!='COMPLETED':
                raise Rejected('CANDIDATE_NOT_VALIDATED')
            current=job.get('qualityEvaluation')
            if current and current['status'] in {'QUEUED','RUNNING'}:
                raise Rejected('QUALITY_EVALUATION_BUSY')
            if current and current['status']=='COMPLETED':
                core=self.core()
                try:return self._evaluation(core,job)
                finally:core.close()
            evaluation_id='evaluation-'+os.urandom(16).hex()
            job['qualityEvaluation']={'id':evaluation_id,'status':'QUEUED','createdAt':now()}
            self.save(job)
            self.pool.submit(self._run_evaluation,job['id'],evaluation_id)
            return copy.deepcopy(job['qualityEvaluation'])

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
        evaluation=self._evaluation(core,job)
        quality=evaluation.get('report')
        quality_passed=quality and quality['decision']=='PASS'
        state=('ISOLATED_PUBLISHED' if published else 'APPROVED' if approval
               else 'QUALITY_PASSED' if quality_passed
               else 'QUALITY_REJECTED' if quality
               else 'EVALUATION_RUNNING' if evaluation['state'] in {'QUEUED','RUNNING'}
               else 'EVALUATION_FAILED' if evaluation['state']=='FAILED'
               else 'EVALUATION_REQUIRED' if valid else 'REVIEW_REQUIRED')
        return {'state':state,
                'candidateDigest':candidate,'validationDigest':val,'approvalDigest':approval,
                'approvalReason':core._get(AUTHOR,approval,'document-approval')['reason'] if approval else None,
                'manifestDigest':manifest,'bindingDigest':binding_sha,'productId':job['id'],
                'qualityAdmissionDigest':quality['admissionDigest'] if quality else None,
                'authority':'ISOLATED_TEST_ONLY','scope':SCOPE,'businessContext':CONTEXT.facts()}

    def get(self, run_id):
        job=super().get(run_id)
        core=self.core()
        try:
            job['release']=self._release(core,job)
            job['qualityEvaluation']=self._evaluation(core,job)
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
        return {**state,'m2':True,'modelReady':self.evaluation_launcher is not None,
                'engineReady':self.evaluation_launcher is not None,'mode':'M2_ISOLATED_DOCUMENT',
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
                    if release['state']=='ISOLATED_PUBLISHED':
                        return release
                    admission=release.get('qualityAdmissionDigest')
                    if release['state']!='QUALITY_PASSED' or not admission:
                        raise Rejected('QUALITY_ADMISSION_REQUIRED')
                    if release['state']!='ISOLATED_PUBLISHED':
                        core.approve_quality_document(REVIEWER,data['candidateDigest'],
                            release['validationDigest'],admission,data['reason'])
                else:
                    if not release.get('approvalDigest'):raise Rejected('DOCUMENT_APPROVAL_REQUIRED')
                    if data['reason']!=release['approvalReason']:raise Rejected('APPROVAL_REASON_MISMATCH')
                    if release['state']!='ISOLATED_PUBLISHED':
                        try:core._source_current(AUTHOR,job['coreObjects']['sourceDigest'],CONTEXT.business_date)
                        except Rejected as exc:
                            if exc.code!='SOURCE_NOT_EFFECTIVE':raise
                            core.activate_source(AUTHOR,job['coreObjects']['sourceDigest'],CONTEXT.business_date)
                        approval=core._get(AUTHOR,release['approvalDigest'],'document-approval')
                        admission=release.get('qualityAdmissionDigest')
                        if (approval['schemaVersion']!='document-approval.v0.2'
                                or approval['qualityAdmissionDigest']!=admission):
                            raise Rejected('DOCUMENT_APPROVAL_MISMATCH')
                        manifest=core.publish_quality_document(AUTHOR,data['candidateDigest'],
                            release['validationDigest'],release['approvalDigest'],admission,1)
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
                def retrieve_candidates(self,*args):return factory().retrieve_candidates(*args)
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
    ap.add_argument('--port',type=int,default=61360)
    ap.add_argument('--isolated-test-preview',action='store_true')
    args=ap.parse_args()
    if not args.isolated_test_preview or args.port in (61353,61357,61358,61359):
        ap.error('Explicit isolated preview and an unreserved port required')
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
