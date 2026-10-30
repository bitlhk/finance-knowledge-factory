"""Start/stop only this preview's own processes; never manage other hosts."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('action',choices=['start','stop'])
    ap.add_argument('--state',type=Path,required=True)
    ap.add_argument('--python',type=Path)
    ap.add_argument('--embedding-python',type=Path)
    ap.add_argument('--private-config',type=Path)
    ap.add_argument('--embedding-cache',type=Path)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
    journal=args.state/'processes.json'
    if args.action=='stop':
        entries=json.loads(journal.read_text()) if journal.exists() else []
        for entry in entries:
            path=Path('/proc')/str(entry['pid'])
            if path.exists() and path.joinpath('stat').read_text().split()[21]==entry['startTime']:
                os.kill(entry['pid'],signal.SIGTERM)
        for _ in range(100):
            live=[]
            for entry in entries:
                path=Path('/proc')/str(entry['pid'])/'stat'
                if path.exists():
                    stat=path.read_text().split()
                    if stat[21]==entry['startTime'] and stat[2]!='Z':live.append(entry)
            if not live:break
            time.sleep(.1)
        else:raise SystemExit('OWNED_PROCESS_STILL_STOPPING')
        print('Only recorded preview/embedding processes signalled; containers and other services unchanged.')
        return
    if not all([args.python,args.embedding_python,args.private_config,args.embedding_cache]):
        raise SystemExit('START_REQUIRES_PYTHON_EMBEDDING_PYTHON_PRIVATE_CONFIG_AND_CACHE')
    with socket.socket() as s:
        s.bind(('127.0.0.1',61353))
    if journal.exists():
        for entry in json.loads(journal.read_text()):
            path=Path('/proc')/str(entry['pid'])/'stat'
            if path.exists() and path.read_text().split()[21]==entry['startTime']:
                raise SystemExit('PREVIEW_ALREADY_RUNNING')
    commands=[('embedding',[str(args.embedding_python),'-m','probes.documents.embedding_service',
        '--credentials',str(args.private_config/'local-credentials.json'),'--state',str(args.state/'embedding'),
        '--cache',str(args.embedding_cache)]),
        ('web',[str(args.python),'-m','m2.web','--state',str(args.state/'app'),
        '--private-config',str(args.private_config)])]
    records=[]
    for name,command in commands:
        with (args.state/(name+'.log')).open('ab') as log:
            child=subprocess.Popen(command,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        records.append({'name':name,'pid':child.pid,'startTime':Path(f'/proc/{child.pid}/stat').read_text().split()[21]})
        journal.write_text(json.dumps(records,indent=2))
        time.sleep(1)
        if child.poll() is not None:raise SystemExit(name.upper()+'_START_FAILED')
    print('Started isolated preview processes. URL: http://127.0.0.1:61353/')


if __name__=='__main__':main()
