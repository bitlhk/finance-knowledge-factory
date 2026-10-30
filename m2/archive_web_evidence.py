"""Export only the fixed synthetic UI experiment, never an arbitrary workspace."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

from knowledge_core.contracts import digest


def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--state',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();root=Path(__file__).resolve().parents[1]
    if args.output.exists():raise SystemExit('EVIDENCE_OUTPUT_ALREADY_EXISTS')
    report=json.loads((args.state/'browser-r2/result.json').read_text())
    expected=hashlib.sha256((root/'tests/fixtures/m2-document.html').read_bytes()).hexdigest()
    if report['run']['sourceId']!=expected:raise SystemExit('FIXED_SYNTHETIC_SOURCE_REQUIRED')
    args.output.mkdir(parents=True)
    for name in ['browser-r1','browser-r2','browser-outage-r1','browser-outage-r2','browser-outage-r3']:
        shutil.copytree(args.state/name,args.output/name)
    db=sqlite3.connect(f'file:{args.state}/app/core.sqlite?mode=ro',uri=True)
    pending=set(s for s in strings(report) if re.fullmatch('[a-f0-9]{64}',s));objects={}
    try:
        while pending:
            sha=pending.pop()
            if sha in objects:continue
            row=db.execute('SELECT kind,body FROM objects WHERE tenant=? AND digest=?',('m2-isolated',sha)).fetchone()
            if not row:continue
            kind,body=row[0],json.loads(row[1])
            if digest(body)!=sha:raise SystemExit('OBJECT_DIGEST_MISMATCH')
            objects[sha]={'kind':kind,'body':body}
            pending.update(s for s in strings(body) if re.fullmatch('[a-f0-9]{64}',s) and s not in objects)
    finally:db.close()
    (args.output/'core-objects.json').write_text(json.dumps(objects,ensure_ascii=False,indent=2)+'\n')
    files={p.relative_to(args.output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(args.output.rglob('*')) if p.is_file()}
    index={'schemaVersion':'m2-web-evidence.v0.1','scope':'REAL_UI_RAGFLOW_CORE_SYNTHETIC_DATA_NOT_HARNESS',
        'codeCommit':'72b8caf','runId':report['run']['id'],'manifestDigest':report['release']['manifestDigest'],
        'sourceSha256':expected,'files':files,'coreObjectCount':len(objects),
        'llmCalls':0,'cost':None,'harnessInstallation':'NOT_COMPLETED',
        'attempts':{'browser-r1':'PASS_UNCOMMITTED_PRECURSOR','browser-r2':'PASS_72b8caf',
            'browser-outage-r1':'SCRIPT_RACE_FAILED_BEFORE_FAULT_INJECTION',
            'browser-outage-r2':'PASS_UNCOMMITTED_PRECURSOR','browser-outage-r3':'PASS_72b8caf'}}
    (args.output/'INDEX.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'files':len(files),'coreObjects':len(objects),'runId':report['run']['id']}))


if __name__=='__main__':main()
