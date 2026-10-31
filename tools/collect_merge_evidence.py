"""Collect only allowlisted, nonsensitive preparation outputs; never copy databases/leases."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--joint',type=Path,required=True)
    args = parser.parse_args()
    target = ROOT/'evidence/main-preparation'
    target.mkdir(parents=True,exist_ok=False)
    paths = [*args.runs.glob('*.xml'), args.runs/'dependency-audit.json',
             args.runs/'equivalence-before.json', args.runs/'equivalence-after.json',
             args.runs/'prefixes/prefix-results.json',
             *args.runs.glob('prefixes/*-fixed.xml'), *args.runs.glob('prefixes/*-fixed.log')]
    for folder in ('browser-01','browser-02','browser-fixed-d','history-http-01'):
        paths += [p for p in (args.runs/folder).iterdir() if p.suffix in ('.json','.png')]
    for path in paths:
        dest = target/path.relative_to(args.runs)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest)
    report = load(args.joint/'report.json')
    binding = load(args.joint/'same-instance-binding.json')
    archive = load(args.joint/'answer-archive-integrity.json')
    assert report['status']=='PASS' and all(c['passed'] for c in report['checks'])
    assert report['buildId']==binding['agentId']
    assert report['instanceId']==binding['instanceId']==archive['instanceId']
    assert binding['installationLock']==archive['runtimeLockDigest']
    assert report['manifest']==binding['manifest']
    chosen = ('status','buildId','instanceId','factoryCommit','builderCommit','builderDirty',
              'harnessCommit','manifest','authentication','historyScope','checks')
    binding_keys = ('agentId','instanceId','manifest','coreReceiptDigest','installationLock','hostRequestId',
                    'authentication','historyOutboundAttempts','modelCallsDuringHistory',
                    'newQueryReceiptsDuringHistory','queryServiceStoppedBeforeHistory')
    save(target/'h1a-saved-linkage.json',{
        'scope':'READ_ONLY_REVIEW_OF_SAVED_H1A_NOT_NEW_AGENT_INSTALLATION',
        'report':{k:report[k] for k in chosen},
        'binding':{k:binding[k] for k in binding_keys},
        'archive':{k:archive[k] for k in ('instanceId','runtimeLockDigest','sha256')},
        'sourceFiles':{str(args.joint/name):sha256((args.joint/name).read_bytes()).hexdigest()
                       for name in ('report.json','same-instance-binding.json','answer-archive-integrity.json','query-events.sse')}})
    prs = json.loads(subprocess.check_output(['gh','pr','list','--repo','bitlhk/finance-knowledge-factory',
        '--state','open','--json','number,baseRefName,headRefName,headRefOid,isDraft,url']))
    save(target/'original-pr-inventory.json',[p for p in prs if 1<=p['number']<=6])
    with urlopen('http://127.0.0.1:61353/api/state',timeout=10) as reply: live=json.load(reply)
    assert live['commit']=='c2939742f211a1ed363dc792d3602d0098765a04' and not live['dirty']
    save(target/'preview-preservation.json',{
        'observationOnly':True,'mutatingRequests':0,
        'live':{k:live[k] for k in ('commit','dirty','prototypeSha256','version')},
        'listeners':subprocess.check_output(['ss','-ltnp','( sport = :61353 or sport = :61359 )'],text=True)})
    suites = {}
    for path in target.rglob('*.xml'):
        suites[str(path.relative_to(target))] = [s.attrib for s in ET.parse(path).getroot().iter('testsuite')]
    before=(target/'equivalence-before.json').read_bytes()
    after=(target/'equivalence-after.json').read_bytes()
    assert before==after
    save(target/'summary.json',{
        'implementationCommit':'b906b78fed9e5d2951df68fcd858866c035806b7',
        'frozenCandidate':'160aaf51b2a54664434d5c17bc3aa95a1b75b693',
        'python':sys.version,'packages':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        'junitSuites':suites,'prefixes':load(args.runs/'prefixes/prefix-results.json'),
        'equivalenceBytesIdentical':True,'equivalenceFileSha256':sha256(before).hexdigest(),
        'historyHttp':{k:load(args.runs/'history-http-01/report.json')[k] for k in
                       ('passed','historyGeneratedQueryReceipts','ragflowCalls','modelCalls','outboundConnectionAttempts')},
        'browser':{'finalStatus':load(args.runs/'browser-fixed-d/result.json')['status'],
                   'scope':'CONTROLLED_UPSTREAM_NOT_NATIVE_RAGFLOW_OR_HARNESS'},
        'failuresRetained':{'unit-c-development.xml':'Missing test helper import, collection error',
                            'browser-01/failure.json':'Controlled in-memory client was recreated before query'},
        'notRerun':['Real LLM extraction','Real Java Flowable','Native RAGFlow ingestion/retrieval','Harness/Builder installation']})
    save(target/'FILES.json',{str(p.relative_to(target)):sha256(p.read_bytes()).hexdigest()
                              for p in sorted(target.rglob('*')) if p.is_file() and p.name!='FILES.json'})
    print(json.dumps({'output':str(target),'fileCount':len(list(target.rglob('*'))),'passed':True}))


if __name__ == '__main__':
    main()
