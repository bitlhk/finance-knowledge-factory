"""Ephemeral browser regression with a controlled upstream, never native RAGFlow."""
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading

from m2.web import DocumentProduction
from tests.test_m2_documents import ControlledClient, CASES
from web_production.server import handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'questions.json').write_text(json.dumps(CASES, ensure_ascii=False))
    instance = ControlledClient()
    instance.operations = [{'operation': 'CONTROLLED_TEST_ONLY'}]
    def client():
        return instance
    with tempfile.TemporaryDirectory(prefix='kf-browser-regression-') as state:
        service = DocumentProduction(state, client)
        http = ThreadingHTTPServer(('127.0.0.1', 0), handler(service))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            subprocess.run(['node', str(Path(__file__).with_name('merge_browser.cjs')),
                            str(args.output), f'http://127.0.0.1:{http.server_port}/'], check=True)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
            service.close()


if __name__ == '__main__':
    main()
