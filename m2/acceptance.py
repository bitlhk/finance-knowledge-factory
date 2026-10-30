"""Bounded real RAGFlow/Core acceptance; not a Builder or UI acceptance test."""
import argparse
import hashlib
import json
import subprocess
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from knowledge_core.core import Actor, BusinessContext
from knowledge_core.contracts import Rejected
from knowledge_core.documents import DocumentCore
from m2.pipeline import produce
from m2.ragflow import Ragflow

CASES = [
    {'question':'合成客服服务时间是什么？','expectedClause':'第一条'},
    {'question':'客户如何申请历史对账单？','expectedClause':'第二条'},
    {'question':'信息缺失时如何处理？','expectedClause':'第三条'},
]
AUTHOR = Actor('m2-isolated','producer','synthetic-authority-not-bank-approved', frozenset({
    'policy.manage','source.register','source.activate','gold.manage','recipe.edit',
    'artifact.produce','candidate.validate','document.approve','manifest.publish','binding.manage'}))
READER = Actor('m2-isolated','knowledge-agent','synthetic-host-not-production')
CONTEXT = BusinessContext('2026-10-30','CN-BJ','synthetic-bank','customer-service','evidence-query','frozen-synthetic-clock')
SCOPE = {'regions':['CN-BJ'],'institutions':['synthetic-bank'],'products':['customer-service'],
         'purposes':['evidence-query'],'validFrom':'2026-01-01','validTo':None,'timezone':'Asia/Shanghai'}


def policy(revision=1, source_access=True):
    grants=[]
    for principal in (AUTHOR.principal,READER.principal):
        grants.append({'principal':principal,'resource':'product:customer-service','actions':['consume','history']})
        if source_access or principal==AUTHOR.principal:
            grants.append({'principal':principal,'resource':'source:customer-service-source','actions':['source_read']})
    return {'schemaVersion':'active-policy.v0.1','revision':revision,'grants':grants}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--private-config',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--verify-outage',action='store_true',
                    help='Stop only the exclusive kf-m1-ragflow_api_1 test container; never restart it.')
    args=ap.parse_args()
    out=args.output
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    raw=(Path(__file__).resolve().parents[1]/'tests/fixtures/m2-document.html').read_bytes()
    core=DocumentCore(out/'core.sqlite')
    client=None
    report={'schemaVersion':'m2-acceptance.v0.1','runId':'m2-'+uuid.uuid4().hex,
        'startedAt':datetime.now(timezone.utc).isoformat(),'sourceDigest':hashlib.sha256(raw).hexdigest(),
        'baseCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'workingTreeDiffDigest':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'])).hexdigest(),
        'status':'FAILED','scope':'REAL_RAGFLOW_AND_CORE_ONLY','cases':CASES,
        'builder':'NOT_EXECUTED','browser':'NOT_EXECUTED','modelCalls':0,
        'approvalAuthority':'ISOLATED_TEST_ONLY','cost':None,'negativeChecks':[]}
    root=Path(__file__).resolve().parents[1]
    report['implementation']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for pattern in ('m2/*.py','knowledge_core/*.py','probes/documents/anchor_bridge.py',
                        'probes/documents/html_evidence.py','tests/fixtures/m2-document.html')
        for p in sorted(root.glob(pattern))}
    components=subprocess.check_output(['docker','inspect','--format',
        '{{json .Name}} {{json .Image}} {{json .Config.Image}}',
        'kf-m1-ragflow_api_1','kf-m1-ragflow_ingestor_1'],text=True)
    report['components']=[dict(zip(('name','imageId','configuredImage'),
        [json.loads(v) for v in line.split()])) for line in components.splitlines()]
    try:
        core.set_policy(AUTHOR,policy(),0)
        client=Ragflow(args.private_config/'local-credentials.json',args.private_config/'http-setup.json')
        data=produce(core,AUTHOR,'customer-service',1,raw,SCOPE,CASES,[READER.principal],client)
        report['objects']=data
        report['index']=core._get(AUTHOR,data['indexDigest'],'document-index')
        def query(manifest, actor=READER, context=CONTEXT):
            return core.query_document(actor,'customer-service',manifest,context,CASES[0]['question'],
                'request-'+uuid.uuid4().hex,'trace-'+report['runId'],client)
        def denied(name, action, expected):
            try: action()
            except Rejected as exc:
                report['negativeChecks'].append({'case':name,'actual':exc.code,'expected':expected,'passed':exc.code==expected})
                if exc.code!=expected: raise
            else: raise Rejected('EXPECTED_REJECTION_MISSING',name)
        denied('unpublished-candidate',lambda:query(data['candidateDigest']),'NOT_FOUND')
        validation=core.validate_document(AUTHOR,data['candidateDigest'],client)
        report['validation']=core._get(AUTHOR,validation,'document-validation')
        if not report['validation']['passed']: raise Rejected('DOCUMENT_VALIDATION_FAILED')
        denied('approval-required',lambda:core.publish_document(AUTHOR,data['candidateDigest'],validation,validation,1),'NOT_FOUND')
        approval=core.approve_document(AUTHOR,data['candidateDigest'],validation,'Frozen synthetic-only M2 acceptance')
        manifest=core.publish_document(AUTHOR,data['candidateDigest'],validation,approval,1)
        report['manifestDigest']=manifest
        report['manifest']=core._get(AUTHOR,manifest,'document-manifest')
        report['bindingDigest']=core.bind_document(AUTHOR,manifest,0)
        denied('registered-not-effective',lambda:query(manifest),'SOURCE_NOT_EFFECTIVE')
        core.activate_source(AUTHOR,data['sourceDigest'],'2026-01-01')
        report['receipts']=[core.query_document(READER,'customer-service',manifest,CONTEXT,c['question'],
            'request-'+uuid.uuid4().hex,'trace-'+report['runId'],client) for c in CASES]
        denied('manifest-mismatch',lambda:query('0'*64),'MANIFEST_MISMATCH')
        denied('unauthorized-user',lambda:query(manifest,replace(READER,principal='outsider')),'FORBIDDEN')
        denied('missing-trusted-context',lambda:query(manifest,context=replace(CONTEXT,source='')),'TRUSTED_CONTEXT_REQUIRED')
        core.set_policy(AUTHOR,policy(2,False),1)
        denied('source-revoked',lambda:query(manifest),'FORBIDDEN')
        core.set_policy(AUTHOR,policy(3,True),2)
        if args.verify_outage:
            stopped=subprocess.run(['docker','stop','--time','10','kf-m1-ragflow_api_1'],
                                   capture_output=True,timeout=30)
            if stopped.returncode: raise Rejected('ISOLATED_API_STOP_FAILED')
            report['isolatedApiStopped']=True
            denied('actual-api-unavailable',lambda:query(manifest),'RAGFLOW_UNAVAILABLE')
        core.close()
        core=DocumentCore(out/'core.sqlite')
        saved=core.replay_document(READER,report['receipts'][0]['receiptDigest'])
        report['restartReplayEqual']=saved['result']==report['receipts'][0]['result']
        if not report['restartReplayEqual']:raise Rejected('REPLAY_MISMATCH')
        report['status']='PASSED_LIMITED_AB_SERVICE_PATH'
    except Rejected as exc:
        report['error']=exc.code
    except Exception as exc:
        report['error']='UNEXPECTED_'+type(exc).__name__
    finally:
        report['operations']=client.operations if client else []
        report['finishedAt']=datetime.now(timezone.utc).isoformat()
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        core.close()
    print(json.dumps({'status':report['status'],'error':report.get('error'),'report':str(out/'report.json')}))
    return 0 if report['status']=='PASSED_LIMITED_AB_SERVICE_PATH' else 1


if __name__=='__main__':
    raise SystemExit(main())
