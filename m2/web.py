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
from business_knowledge.boc_amsylj01 import build_bundle, verify_bundle
from business_knowledge import cmbwm_132112
from m2.workbench_authority import WorkbenchAuthorities
from m2.pipeline import produce, parse
from m2.ragflow import Ragflow
from web_production.engine import Production, now, persist
from web_production.server import handler


class DocumentProduction(Production):
    m2 = True

    def __init__(self, state, client_factory, evaluation_launcher=None,
                 authorities=None):
        self.database=Path(state)/'core.sqlite'
        self.client_factory=client_factory
        self.evaluation_launcher=evaluation_launcher
        self.authorities=authorities or WorkbenchAuthorities.synthetic()
        self.producer=self.authorities.producer
        self.reader=self.authorities.reader
        self.context=self.authorities.context
        self.scope=self.authorities.scope
        super().__init__(state, caller=lambda _: (_ for _ in ()).throw(Rejected('DOCUMENT_ONLY_REQUIRED')))
        self.core().close()

    def core(self):
        return DocumentCore(self.database)

    def recipe_metadata(self, data):
        return {'documentPipeline':'native-ragflow+verified-html-anchors.v0.1',
                'delivery':'CORE_ISOLATED_DOCUMENT_CANDIDATE',
                'trustedContext':self.context.facts(),
                'approvalAuthority':('ISOLATED_TEST_ONLY' if self.authorities.isolated
                                     else 'TRUSTED_SERVER_AUTHENTICATION')}

    def business_sample(self, sample_id, authority=None):
        authority=authority or self.authorities.authenticate('candidate.produce')
        if sample_id!='boc-amsylj01':
            raise Rejected('BUSINESS_SAMPLE_NOT_FOUND')
        root=Path(__file__).parents[1]/'examples/business/customer-manager'
        source_root=root/'amsylj01/sources'
        generated=root/'amsylj01/generated'
        bundle=build_bundle(source_root)
        provenance=json.loads((generated/'amsylj01-provenance.json').read_text())
        verify_bundle(source_root,(generated/'amsylj01-derived.html').read_bytes(),
                      provenance)
        register=json.loads((root/'boc-amsylj01-source-register.json').read_text())
        business=json.loads((root/'boc-wealth-manager-test-set-v0.1.json').read_text())
        aliases={item['clause']:item['coreClause'] for item in provenance['mappings']}
        tests=[{'question':item['question'],
                'expectedClause':aliases[item['requiredEvidence'][0]]}
               for item in business['cases'] if item.get('requiredEvidence')]
        source=self.source(register['title'],bundle['html'].decode(),{
            'officialUrl':register['sources'][0]['url'],
            'institution':register['institution'],
            'documentDate':register['sources'][0]['documentDate'],
            'version':'AMSYLJ01 · 公开资料固定版本',
            'authorityStatus':register['authorityStatus']})
        with self.lock:
            stored=self.sources[source['id']]
            stored['businessProduct']={
                'productId':register['productId'],
                'sourceCount':len(register['sources']),
                'qualityCaseCount':len(business['cases']),
                'provenanceDigest':provenance['provenanceDigest'],
                'sourceDigests':[item['sha256'] for item in register['sources']],
                'currentSaleStatus':'REQUIRES_LIVE_PRODUCT_SYSTEM'}
            stored['importedBy']=self.authorities.audit(authority)
            persist(self.state/('source-'+source['id']+'.json'),stored)
            source=self.public_source(stored)
        return {'source':source,'tests':tests,
                'qualityCaseCount':len(business['cases'])}

    def import_business_product(self, data, authority=None):
        authority=authority or self.authorities.authenticate('candidate.produce')
        if (not isinstance(data,dict) or set(data)!={'registrationId','files'}
                or data['registrationId']!=cmbwm_132112.REGISTRATION_ID):
            raise Rejected('BUSINESS_PRODUCT_REGISTRATION_INVALID')
        values=cmbwm_132112.decode_uploads(data['files'])
        bundle=cmbwm_132112.build_bundle(values)
        metadata={
            'officialUrl':cmbwm_132112.SOURCES['sales-documents']['url'],
            'institution':'南京银行（销售文件披露渠道）/招银理财（管理人）',
            'documentDate':'2026-10-30',
            'version':'132112 · 2026-10-30 固定资料包',
            'authorityStatus':'PUBLIC_SOURCE_REQUIRES_CURRENT_BUSINESS_REVALIDATION'}
        source=self.source(cmbwm_132112.TITLE,bundle['html'].decode(),metadata)
        import_root=self.state/'imports'/source['id']
        import_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        for source_id,value in values.items():
            target=import_root/cmbwm_132112.SOURCES[source_id]['filename']
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=hashlib.sha256(value).hexdigest():
                raise Rejected('BUSINESS_SOURCE_STORAGE_CHANGED')
            target.write_bytes(value)
            target.chmod(0o600)
        with self.lock:
            stored=self.sources[source['id']]
            stored['businessProduct']={
                'registrationId':cmbwm_132112.REGISTRATION_ID,
                'productId':cmbwm_132112.PRODUCT_ID,
                'productCode':'132112',
                'salesCodes':['132112D','132112MS','132112N'],
                'sourceCount':len(cmbwm_132112.SOURCES),
                'qualityCaseCount':len(bundle['tests']),
                'provenanceDigest':bundle['provenance']['provenanceDigest'],
                'sourceDigests':[item['sha256'] for item in bundle['provenance']['sourceFiles']],
                'sourceFiles':bundle['provenance']['sourceFiles'],
                'sourceReferences':bundle['sourceReferences'],
                'currentSaleStatus':'REQUIRES_LIVE_PRODUCT_SYSTEM'}
            stored['importedBy']=self.authorities.audit(authority)
            persist(self.state/('source-'+source['id']+'.json'),stored)
            source=self.public_source(stored)
        return {'source':source,'tests':bundle['tests'],
                'qualityCaseCount':len(bundle['tests'])}

    def submit(self, data, authority=None):
        authority=authority or self.authorities.authenticate('candidate.produce')
        if data.get('rules') is not False or data.get('clauses') or data.get('modelConsent') is not False:
            raise Rejected('DOCUMENT_ONLY_REQUIRED')
        if not data.get('tests'):
            raise Rejected('RETRIEVAL_GOLD_REQUIRED')
        with self.lock:
            if len(self.jobs)>=20 and not any(j['requestId']==data.get('requestId') for j in self.jobs.values()):
                raise Rejected('ISOLATED_RUN_LIMIT')
            result=super().submit(data)
            job=self.jobs[result['id']]
            requested=self.authorities.audit(authority)
            if job.get('requestedBy') and job['requestedBy']!=requested:
                raise Rejected('IDEMPOTENCY_IDENTITY_MISMATCH')
            if not job.get('requestedBy'):
                job['requestedBy']=requested
                self.save(job)
            return copy.deepcopy(job)

    def _grant_product(self, core, product):
        revision,sha=core._head(self.producer,'policy','current')
        grants=core._get(self.producer,sha,'active-policy')['grants'] if sha else []
        principals=(self.producer.principal,self.reader.principal)
        if self.authorities.isolated:
            principals += (self.authorities.authenticate('document.approve').principal,)
        for principal in principals:
            grants += [{'principal':principal,'resource':'product:'+product,'actions':['consume','history']},
                       {'principal':principal,'resource':'source:'+product+'-source','actions':['source_read']}]
        core.set_policy(self.producer,{'schemaVersion':'active-policy.v0.1','revision':revision+1,'grants':grants},revision)

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
            business=self.sources[job['sourceId']].get('businessProduct') or {}
            objects=produce(core,self.producer,run_id,1,raw,self.scope,job['recipe']['tests'],
                [self.reader.principal],client,business.get('sourceReferences'))
            index=core._get(self.producer,objects['indexDigest'],'document-index')
            with self.lock:
                job['coreObjects']=objects
                job['nativeOperations']=copy.deepcopy(getattr(client,'operations',[]))
                self.save(job)
            self.stage(job,'documents','COMPLETED',datasetId=index['index']['datasetId'],
                       documentId=index['index']['documentId'],chunkCount=len(index['index']['chunks']))
            self.stage(job,'rules','NOT_SELECTED')
            self.stage(job,'validation','RUNNING')
            validation=core.validate_document(self.producer,objects['candidateDigest'],client)
            result=core._get(self.producer,validation,'document-validation')
            artifact={'schemaVersion':'m2-document-display.v0.1','documentClauses':clauses,'rules':[],
                'candidateDigest':objects['candidateDigest'],'indexDigest':objects['indexDigest'],
                'source':core._get(self.producer,objects['sourceDigest'],'source-revision'),'bridge':index['bridge'],
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
                           nativeOperations=copy.deepcopy(getattr(client,'operations',[])) if client else [])
                self.save(job)
        finally:
            core.close()

    def _latest(self, core, kind, candidate):
        rows=core.db.execute('SELECT digest FROM objects WHERE tenant=? AND kind=? AND json_extract(body,\'$.candidateDigest\')=? ORDER BY rowid DESC LIMIT 1',
                            (self.producer.tenant,kind,candidate)).fetchall()
        return rows[0][0] if rows else None

    def _quality_report(self, core, candidate, admission_digest):
        admission=core._get(self.producer,admission_digest,'document-quality-admission')
        if admission['candidateDigest']!=candidate:
            raise Rejected('QUALITY_ADMISSION_FAILED_OR_MISMATCH')
        answer=core._get(self.producer,admission['answerEvaluationDigest'],'document-answer-evaluation')
        runtime_kind=core.db.execute('SELECT kind FROM objects WHERE tenant=? AND digest=?',
            (self.producer.tenant,answer['runtimeEvidenceDigest'])).fetchone()
        if not runtime_kind or runtime_kind[0] not in {
                'document-answer-runtime-evidence','document-factory-evaluation-runtime-evidence'}:
            raise Rejected('QUALITY_RUNTIME_EVIDENCE_INVALID')
        runtime=core._get(self.producer,answer['runtimeEvidenceDigest'],runtime_kind[0])
        retrieval=core._get(self.producer,admission['retrievalEvaluationDigest'],
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

    def start_evaluation(self, data, authority=None):
        authority=authority or self.authorities.authenticate('evaluation.start')
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
            job['qualityEvaluation']={'id':evaluation_id,'status':'QUEUED','createdAt':now(),
                                      'requestedBy':self.authorities.audit(authority)}
            self.save(job)
            self.pool.submit(self._run_evaluation,job['id'],evaluation_id)
            return copy.deepcopy(job['qualityEvaluation'])

    def _release(self, core, job):
        objects=job.get('coreObjects')
        if not objects:return {'state':'NO_CANDIDATE'}
        candidate=objects['candidateDigest']
        core._document_parts(self.producer,candidate)
        val=self._latest(core,'document-validation',candidate)
        approval=self._latest(core,'document-approval',candidate)
        binding_sha=core._head(self.producer,'document-binding',job['id'])[1]
        binding=core._get(self.producer,binding_sha,'document-binding') if binding_sha else None
        manifest=binding['manifestDigest'] if binding else None
        published=bool(manifest)
        if manifest:
            frozen=core._get(self.producer,manifest,'document-manifest')
            if frozen['candidateDigest']!=candidate:raise Rejected('CANDIDATE_MISMATCH')
            val,approval=frozen['validationDigest'],frozen['approvalDigest']
        elif approval and core._get(self.producer,approval,'document-approval')['validationDigest']!=val:
            approval=None
        valid=core._get(self.producer,val,'document-validation')['passed'] if val else False
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
                'approvalReason':core._get(self.producer,approval,'document-approval')['reason'] if approval else None,
                'manifestDigest':manifest,'bindingDigest':binding_sha,'productId':job['id'],
                'qualityAdmissionDigest':quality['admissionDigest'] if quality else None,
                'authority':('ISOLATED_TEST_ONLY' if self.authorities.isolated
                             else 'TRUSTED_SERVER_AUTHENTICATION'),
                'scope':self.scope,'businessContext':self.context.facts(),
                'sourceActivationDigest':job.get('sourceActivationDigest')}

    def get(self, run_id):
        job=super().get(run_id)
        core=self.core()
        try:
            job['release']=self._release(core,job)
            job['qualityEvaluation']=self._evaluation(core,job)
            rows=core.db.execute("SELECT digest FROM objects WHERE tenant=? AND kind='document-receipt' AND json_extract(body,'$.productId')=? ORDER BY rowid",(self.reader.tenant,run_id))
            job['consumptionReceipts']=[self._receipt(core.replay_document(self.reader,row[0]),run_id) for row in rows.fetchall()]
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

    def activate_source(self, data, authority=None):
        authority=authority or self.authorities.authenticate('source.activate')
        if set(data)!={'runId','candidateDigest','reason'} or not isinstance(data['reason'],str) or not 1<=len(data['reason'].strip())<=1000:
            raise Rejected('SOURCE_ACTIVATION_CONTRACT_INVALID')
        with self.lock:
            job=super().get(data['runId'])
            if job['status']!='COMPLETED':raise Rejected('CANDIDATE_NOT_VALIDATED')
            if job.get('sourceActivationDigest'):
                raise Rejected('SOURCE_ACTIVATION_REPLAY')
            if job.get('coreObjects',{}).get('candidateDigest')!=data['candidateDigest']:
                raise Rejected('CANDIDATE_MISMATCH')
            core=self.core()
            try:
                release=self._release(core,job)
                if release['state']!='APPROVED':
                    raise Rejected('DOCUMENT_APPROVAL_REQUIRED')
                source=job['coreObjects']['sourceDigest']
                try:
                    activation=core._source_current(self.producer,source,
                                                    self.context.business_date)
                except Rejected as exc:
                    if exc.code!='SOURCE_NOT_EFFECTIVE':raise
                    activation=core.activate_source(authority,source,
                                                    self.context.business_date)
                job=self.jobs[data['runId']]
                job['sourceActivationDigest']=activation
                job['sourceActivatedBy']=self.authorities.audit(authority)
                job['sourceActivationReason']=data['reason'].strip()
                self.save(job)
                return self._release(core,job)
            finally:core.close()

    def release_action(self, path, data, authority=None):
        if path not in {'/api/document-approve','/api/document-publish'}:raise Rejected('RELEASE_CONTRACT_INVALID')
        operation=('document.approve' if path=='/api/document-approve'
                   else 'manifest.publish')
        authority=authority or self.authorities.authenticate(operation)
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
                        self.authorities.check_separation(job.get('requestedBy'),authority)
                        core.approve_quality_document(authority,data['candidateDigest'],
                            release['validationDigest'],admission,data['reason'],1)
                else:
                    if not release.get('approvalDigest'):raise Rejected('DOCUMENT_APPROVAL_REQUIRED')
                    if data['reason']!=release['approvalReason']:raise Rejected('APPROVAL_REASON_MISMATCH')
                    if release['state']!='ISOLATED_PUBLISHED':
                        core._source_current(self.producer,job['coreObjects']['sourceDigest'],
                                             self.context.business_date)
                        approval=core._get(authority,release['approvalDigest'],'document-approval')
                        admission=release.get('qualityAdmissionDigest')
                        if (approval['schemaVersion']!='document-approval.v0.3'
                                or approval['qualityAdmissionDigest']!=admission):
                            raise Rejected('DOCUMENT_APPROVAL_MISMATCH')
                        manifest=core.publish_quality_document(authority,data['candidateDigest'],
                            release['validationDigest'],release['approvalDigest'],admission,1,
                            self.context.business_date)
                        core.bind_document(authority,manifest,0)
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
            receipt=core.query_document(self.reader,run_id,job['release']['manifestDigest'],self.context,query,
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
