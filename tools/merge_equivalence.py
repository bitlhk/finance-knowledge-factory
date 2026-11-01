"""Emit deterministic document lifecycle outputs from the caller's Git worktree."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path.cwd()))
import knowledge_core.core as base_core
import knowledge_core.documents as document_core
from knowledge_core.contracts import digest, Rejected
from knowledge_core.documents import DocumentCore
from m2.pipeline import produce
from tests.test_m2_documents import ControlledClient, RAW, CASES, AUTHOR, READER, CONTEXT, ir, policy


class FixedTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 30, 1, 0, 0, tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base_core.datetime = document_core.datetime = FixedTime
    with tempfile.TemporaryDirectory(prefix='kf-equivalence-') as directory:
        core, client = DocumentCore(Path(directory)/'core.sqlite'), ControlledClient()
        try:
            core.set_policy(AUTHOR, policy(), 0)
            produced = produce(core, AUTHOR, 'faq', 1, RAW, ir()['rules'][0]['scope'], CASES, ['reader'], client)
            core.activate_source(AUTHOR, produced['sourceDigest'], '2026-01-01')
            validation = core.validate_document(AUTHOR, produced['candidateDigest'], client)
            approval = core.approve_document(AUTHOR, produced['candidateDigest'], validation, 'Synthetic equivalence only')
            manifest = core.publish_document(AUTHOR, produced['candidateDigest'], validation, approval, 1)
            core.bind_document(AUTHOR, manifest, 0)
            receipt = core.query_document(READER, 'faq', manifest, CONTEXT, CASES[0]['question'],
                                          'fixed-request', 'fixed-trace', client)
            calls = client.calls
            replay = core.replay_document(READER, receipt['receiptDigest'])
            assert client.calls == calls and replay['result'] == receipt['result']
            core.set_policy(AUTHOR, policy(2, source_reader=False), 1)
            denied = []
            for name, action in [('query', lambda: core.query_document(READER,'faq',manifest,CONTEXT,
                                    CASES[0]['question'],'denied','denied',client)),
                                 ('history', lambda: core.replay_document(READER,receipt['receiptDigest']))]:
                try: action()
                except Rejected as exc: denied.append({'operation':name,'code':exc.code})
                else: raise AssertionError('Revocation must deny')
            assert client.calls == calls
            objects = core.db.execute('SELECT tenant,kind,digest,body FROM objects ORDER BY tenant,kind,digest').fetchall()
            result = {'produced':produced,'validation':validation,'approval':approval,'manifest':manifest,
                      'receipt':receipt,'replay':replay,'denied':denied,'retrievalCalls':calls,
                      'storedObjects':objects,'storedObjectsDigest':digest(objects),
                      'scope':'CONTROLLED_EQUIVALENCE_FIXED_CLOCK_NOT_NEW_NATIVE_ACCEPTANCE'}
        finally: core.close()
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'digest':digest(result),'objectCount':len(objects),'passed':True}))


if __name__ == '__main__':
    main()
