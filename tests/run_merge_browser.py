"""Isolated browser regression; native RAGFlow requires explicit private config."""
import argparse
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading

from m2.web import DocumentProduction
from m2.process_support import code_identity
from tests.test_m2_documents import ControlledClient, CASES
from web_production.server import handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--guided', action='store_true')
    parser.add_argument('--native-config', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'questions.json').write_text(json.dumps(CASES, ensure_ascii=False))
    if args.native_config:
        from m2.ragflow import Ragflow
        def client():
            return Ragflow(args.native_config/'local-credentials.json', args.native_config/'http-setup.json')
    else:
        instance = ControlledClient()
        instance.operations = [{'operation': 'CONTROLLED_TEST_ONLY'}]
        def client():
            return instance
    root = Path(__file__).resolve().parents[1]
    provenance = {'code': code_identity(), 'upstream': 'NATIVE_RAGFLOW' if args.native_config else 'CONTROLLED',
                  'guided': args.guided, 'files': {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
                  for p in [root/'m2/web.js', root/'web_production/app.js', Path(__file__), Path(__file__).with_name('merge_browser.cjs')]}}
    (args.output/'provenance.json').write_text(json.dumps(provenance, indent=2))
    with tempfile.TemporaryDirectory(prefix='kf-browser-regression-') as state:
        service = DocumentProduction(state, client)
        http = ThreadingHTTPServer(('127.0.0.1', 0), handler(service))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            subprocess.run(['node', str(Path(__file__).with_name('merge_browser.cjs')),
                            str(args.output), f'http://127.0.0.1:{http.server_port}/',
                            'guided' if args.guided else 'upload',
                            'native' if args.native_config else 'controlled'], check=True)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
            service.close()


if __name__ == '__main__':
    main()
