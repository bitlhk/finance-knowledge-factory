"""Test each committed merge prefix in its own detached worktree, not the source service."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UNITS = [('A','116e69f'),('B','684217c'),('C','02e59a5'),('D','b906b78')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    reports = []
    for unit, ref in UNITS:
        sha = subprocess.check_output(['git','rev-parse',ref],cwd=ROOT,text=True).strip()
        tree = args.output/f'unit-{unit.lower()}'
        subprocess.run(['git','worktree','add','--detach',str(tree),sha],cwd=ROOT,check=True)
        xml = args.output/f'unit-{unit.lower()}-fixed.xml'
        command = [sys.executable,'-m','pytest','-q',f'--junitxml={xml}']
        started = time.time()
        with (args.output/f'unit-{unit.lower()}-fixed.log').open('x') as log:
            result = subprocess.run(command,cwd=tree,stdout=log,stderr=subprocess.STDOUT)
        suite = ET.parse(xml).getroot().find('testsuite')
        report = {'unit':unit,'commit':sha,'exitCode':result.returncode,'command':command,
                  'seconds':round(time.time()-started,3),'suite':suite.attrib}
        reports.append(report)
        (args.output/'prefix-results.json').write_text(json.dumps(reports,indent=2)+'\n')
        print(json.dumps(report),flush=True)
        if result.returncode: raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
