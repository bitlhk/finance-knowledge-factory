#!/usr/bin/env python3
"""Re-evaluate archived Harness answers without rerunning retrieval or a model."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge_core.contracts import digest
from knowledge_core.core import Actor
from knowledge_core.documents import DocumentCore
from quality.retrieval_profiles import PROFILES


AUTHOR = Actor('m2-isolated', 'quality-author', 'quality-replay-authority-v1', frozenset({
    'candidate.validate',
}))


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retrieval-evaluation', type=Path, required=True)
    args = parser.parse_args()

    root = args.acceptance_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f'output already exists: {output}')
    output.mkdir(parents=True)
    database = output / 'runtime-evidence-core-v02.sqlite'
    source_database = sqlite3.connect(root / 'runtime-evidence-core.sqlite')
    target_database = sqlite3.connect(database)
    try:
        source_database.backup(target_database)
    finally:
        target_database.close()
        source_database.close()

    old_runtime = read_json(root / 'acceptance-final-runtime-evidence.json')['body']
    old_answer_quality_path = root / 'acceptance-final-answer-quality.json'
    old_answer_quality_raw = old_answer_quality_path.read_bytes()
    old_answer_quality = json.loads(old_answer_quality_raw)
    answers = read_json(root / 'acceptance-final-answers.json')
    by_case = {item['case']['caseId']:item for item in answers}
    candidate = root / 'studio' / 'workbench' / old_runtime['buildId'] / 'candidate'
    runs = []
    for case in old_runtime['cases']:
        request_id = by_case[case['caseId']]['response']['result']['answerArchive']['requestId']
        matches = list((root / 'studio' / 'execution-history').glob(f'*/{request_id}.jsonl'))
        if len(matches) != 1:
            raise SystemExit(f'expected one archived history for {request_id}, found {len(matches)}')
        history_root = matches[0].parent
        history_rows = [json.loads(line) for line in
                        (history_root / f'{request_id}.jsonl').read_text().splitlines()]
        runs.append({'caseId':case['caseId'],
                     'archive':read_json(history_root / f'{request_id}.knowledge-answer.json'),
                     'historyRows':history_rows,
                     'runtimeLockRaw':(history_root / f'{request_id}.runtime-lock.json').read_bytes()})

    profile = {'schemaVersion':'document-quality-profile.v0.1',
               'id':'financial-document-v02', 'revision':1,
               'config':PROFILES['financial-document-v02']}
    retrieval = read_json(args.retrieval_evaluation)
    if digest(profile) != retrieval['profileDigest']:
        raise SystemExit('profile digest does not match the archived retrieval evaluation')

    core = DocumentCore(database)
    try:
        with core.tx():
            profile_digest = core._put(AUTHOR, 'document-quality-profile', profile)
            retrieval_digest = core._put(AUTHOR, 'document-retrieval-evaluation', retrieval)
        runtime_digest = core.register_answer_runtime_evidence(
            AUTHOR, old_runtime['candidateDigest'], old_runtime['testSetDigest'],
            old_runtime['manifestDigest'], (candidate / 'service-lock.json').read_bytes(),
            (candidate / 'model-selection.json').read_bytes(), runs,
            read_json(root / 'acceptance-final-stopped.json'))
        answer_digest = core.register_answer_evaluation(
            AUTHOR, old_runtime['candidateDigest'], profile_digest,
            old_runtime['testSetDigest'], retrieval_digest, runtime_digest)
        admission_digest = core.assess_document_quality(
            AUTHOR, old_runtime['candidateDigest'], profile_digest,
            old_runtime['testSetDigest'], retrieval_digest, answer_digest)
        runtime = core._get(AUTHOR, runtime_digest, 'document-answer-runtime-evidence')
        answer = core._get(AUTHOR, answer_digest, 'document-answer-evaluation')
        admission = core._get(AUTHOR, admission_digest, 'document-quality-admission')
    finally:
        core.close()

    write_json(output / 'runtime-evidence-v02.json', {'digest':runtime_digest, 'body':runtime})
    write_json(output / 'answer-evaluation-v02.json', {'digest':answer_digest, 'body':answer})
    write_json(output / 'quality-admission-v02.json', {'digest':admission_digest, 'body':admission})
    summary = {
        'schemaVersion':'document-answer-quality-replay.v0.2',
        'sourceRuntimeEvidenceDigest':digest(old_runtime),
        'sourceAnswerEvaluation':{
            'artifactSha256':hashlib.sha256(old_answer_quality_raw).hexdigest(),
            'decision':old_answer_quality['decision'],
            'passed':old_answer_quality['passed'],
            'total':old_answer_quality['total'],
        },
        'runtimeEvidenceDigest':runtime_digest,
        'answerEvaluationDigest':answer_digest,
        'qualityAdmissionDigest':admission_digest,
        'decision':admission['decision'],
        'passed':sum(case['classification'] in ('CORRECT', 'CORRECT_REFUSAL')
                     for case in answer['cases']),
        'total':len(answer['cases']),
        'instanceId':runtime['instanceId'],
        'installationLockDigest':runtime['installationLockDigest'],
        'manifestDigest':runtime['manifestDigest'],
        'modelIdentity':runtime['modelIdentity'],
        'reexecuted':{'retrieval':False, 'model':False},
        'originalArchivesChanged':False,
    }
    write_json(output / 'replay-summary-v02.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
