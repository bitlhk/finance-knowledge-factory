"""Default-path isolation and unchanged frozen evidence, not rule acceptance."""
import ast
from hashlib import sha256
import importlib
from pathlib import Path
import subprocess
import sys

import pytest

from knowledge_core.contracts import Rejected

ROOT = Path(__file__).resolve().parents[1]


def test_default_modules_do_not_import_experiments():
    script = '''
import importlib, sys
for name in ['knowledge_core.documents','m2.pipeline','m2.harness_runtime',
 'm2.history_runtime','m2.history_service','m2.web','web_production.server']:
 importlib.import_module(name)
assert not any(k == 'probes' or k.startswith('probes.') for k in sys.modules)
'''
    subprocess.run([sys.executable, '-c', script], cwd=ROOT, check=True)
    assert not (ROOT / 'probes').exists()


def test_import_graph_has_no_experimental_edges():
    for folder in ('knowledge_core', 'm2', 'web_production'):
        for path in (ROOT/folder).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or '').startswith(('probes', 'web_preview.server'))
                if isinstance(node, ast.Import):
                    assert all(not item.name.startswith('probes') for item in node.names)


def test_rule_experiments_cannot_run_even_with_credentials(tmp_path, monkeypatch):
    from web_production.engine import Production
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-not-a-key')
    monkeypatch.setenv('KNOWLEDGE_FLOWABLE_CLASSPATH', '/does/not/exist')
    p = Production(tmp_path, caller=lambda _: pytest.fail('Experimental call forbidden'))
    try:
        source = p.source('Synthetic', '<html><p>第一条 期限不得超过十二个月。</p></html>')
        with pytest.raises(Rejected, match='RULE_EXPERIMENT_ISOLATED'):
            p.submit({'requestId':'isolated-rule-test','sourceId':source['id'],'rules':True,
                      'clauses':['第一条'],'tests':[],'modelConsent':True})
        with pytest.raises(Rejected, match='RULE_EXPERIMENT_ISOLATED'):
            p.rule_test('run', '第一条', 'rule', {})
        assert not p.snapshot()['modelReady'] and not p.snapshot()['engineReady']
        assert not p.jobs
    finally: p.close()


@pytest.mark.parametrize('module', ['m2.web','web_production.server'])
def test_preview_requires_explicit_test_mode(module, tmp_path, monkeypatch):
    target = importlib.import_module(module)
    args = [module, '--state', str(tmp_path)]
    if module == 'm2.web': args += ['--private-config', str(tmp_path)]
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(SystemExit): target.main()
    monkeypatch.setattr(sys, 'argv', args + ['--isolated-test-preview', '--port', '61353'])
    with pytest.raises(SystemExit): target.main()
    assert not (tmp_path/'core.sqlite').exists()


def test_frozen_runtime_and_ui_sha():
    expected = {
        'contracts/runtime/knowledge-history-v0.1.proposed.schema.json': '114397ec532e40b84975e5884457ed1de63b45c71a05652c7e8ed5c3f1f3c3c6',
        'contracts/runtime/knowledge-runtime-v0.1.schema.json': 'ae9fa3dbf053829144983f3d23892eeef93d43e1a755f0306ccd0a01a209c4fa',
        'web_preview/baseline/v1.5.html': 'a12cf30a5771b59cd9fabb00ea67d1bc84361d2a73c916c354593b1adc15eb80'}
    for path, sha in expected.items(): assert sha256((ROOT/path).read_bytes()).hexdigest() == sha
