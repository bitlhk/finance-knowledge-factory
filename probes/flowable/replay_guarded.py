"""Expected failed gold must still produce a full real-engine probe report."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path('.m1-local/flowable')
    before = set(root.iterdir()) if root.exists() else set()
    process = subprocess.run([sys.executable, '-m', 'probes.flowable.run', '--request',
                              'evidence/m1-round3/policy/full-clause/engine-request.json'], timeout=660)
    created = set(root.iterdir()) - before
    assert len(created) == 1
    report = json.loads((created.pop() / 'response.json').read_text())
    assert process.returncode != 0, 'The retained failures must not become passes'
    assert len(report['results']) == 24
    assert sum(r['passed'] for r in report['results']) == 18
    assert report['engineCalls'] == 0
    assert report['sameEngineRecovery'] is None
    assert report['recoveryStatus'] == 'NOT_EXECUTED_NO_ELIGIBLE_CASE'
    assert all(r['rejected'] for r in report['faultResults'])
    print('Guard-only runner preserves 6 expected gold failures, complete report, no false recovery claim.')


if __name__ == '__main__':
    main()
