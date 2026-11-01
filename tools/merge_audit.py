"""Read-only Git/AST provenance audit for the main-based preparation candidate."""
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess

SOURCE = '160aaf51b2a54664434d5c17bc3aa95a1b75b693'
BASE = 'bd725263e4c7d28b14fba9e665d9d180e68e84c8'
ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def files(ref):
    return git('ls-tree', '-r', '--name-only', ref).decode().splitlines()


def body(ref, path):
    return git('show', f'{ref}:{path}')


def imports(ref):
    result = {}
    for path in files(ref):
        if not path.endswith('.py') or not path.startswith(('knowledge_core/', 'm2/', 'web_production/', 'web_preview/', 'probes/')):
            continue
        edges = []
        for node in ast.walk(ast.parse(body(ref, path))):
            if isinstance(node, ast.ImportFrom):
                edges.append({'line': node.lineno, 'module': '.'*node.level+(node.module or ''),
                              'names': [alias.name for alias in node.names]})
            elif isinstance(node, ast.Import):
                edges.extend({'line': node.lineno, 'module': alias.name} for alias in node.names)
        result[path] = edges
    return result


def without_imports(data):
    tree = ast.parse(data)
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    return ast.dump(tree, include_attributes=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate = git('rev-parse', args.candidate).decode().strip()
    original, selected = files(SOURCE), files(candidate)
    selected_set = set(selected)
    mappings = {'knowledge_core/evidence/html_evidence.py': 'probes/documents/html_evidence.py',
                'knowledge_core/evidence/anchor_bridge.py': 'probes/documents/anchor_bridge.py'}
    audit = []
    for path in selected:
        source_path = mappings.get(path, path)
        current = body(candidate, path)
        prior = body(SOURCE, source_path) if source_path in original else None
        audit.append({'target': path, 'source': source_path if prior is not None else None,
                      'sha256': sha256(current).hexdigest(),
                      'sourceSha256': sha256(prior).hexdigest() if prior is not None else None,
                      'byteIdentical': current == prior if prior is not None else None})
    evidence = [p for p in original if p.startswith('evidence/')]
    assert all(p in selected_set and body(SOURCE,p) == body(candidate,p) for p in evidence)
    frozen = [p for p in files(BASE) if p.startswith(('knowledge_core/', 'contracts/'))]
    assert all(body(BASE,p) == body(candidate,p) for p in frozen)
    contracts = [p for p in original if p.startswith('contracts/runtime/')]
    assert all(body(SOURCE,p) == body(candidate,p) for p in contracts)
    ui = ['web_preview/baseline/v1.5.html', 'web_production/index.html',
          'web_production/app.js','web_production/workshop.js','web_production/style.css','m2/web.js']
    assert all(body(SOURCE,p) == body(candidate,p) for p in ui)
    equivalent = []
    for path in ['knowledge_core/documents.py','knowledge_core/document_contracts.py',
                 'm2/pipeline.py','m2/ragflow.py','m2/harness_runtime.py','m2/host_leases.py',
                 'm2/runtime_protocol.py','m2/history_runtime.py','m2/history_service.py', *mappings]:
        same = without_imports(body(SOURCE,mappings.get(path,path))) == without_imports(body(candidate,path))
        assert same, path
        equivalent.append(path)
    after = imports(candidate)
    forbidden = [(p,e) for p,edges in after.items() for e in edges
                 if e['module'].startswith(('probes','web_preview.server'))]
    assert not forbidden and not any(p.startswith('probes/') for p in selected)
    history = []
    for sha in git('rev-list','--reverse',f'{BASE}..{SOURCE}').decode().splitlines():
        history.append({'commit':sha,'parents':git('show','-s','--format=%P',sha).decode().strip().split(),
                        'subject':git('show','-s','--format=%s',sha).decode().strip(),
                        'paths':git('diff-tree','--no-commit-id','--name-only','-r',sha).decode().splitlines()})
    report = {'base':BASE,'frozenSource':SOURCE,'candidate':candidate,
        'sourceCommitChain':history,'importsBefore':imports(SOURCE),'importsAfter':after,
        'pathProvenance':audit,'excludedSourcePaths':[p for p in original if p not in selected_set],
        'preservedEvidenceFiles':len(evidence),'frozenM0Files':frozen,
        'byteIdenticalRuntimeContracts':contracts,'byteIdenticalUi':ui,
        'sameAstExceptImports':equivalent,'forbiddenImports':forbidden,
        'scope':'STATIC_PROVENANCE_NOT_NEW_COMPONENT_OR_BUSINESS_ACCEPTANCE'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'candidate':candidate,'commits':len(history),'evidenceFiles':len(evidence),
                      'sameAstModules':len(equivalent),'passed':True}))


if __name__ == '__main__':
    main()
