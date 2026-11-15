"""Disposable synthetic fixture for browser CI; no real provider or credentials."""
import os
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_published_workbench import fixture_catalog
from test_public_workbench_readonly import NoBusinessCalls
from web_production.server import handler


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with TemporaryDirectory(prefix='kf-browser-') as directory:
        os.environ['KF_WORKBENCH_CATALOG'] = fixture_catalog(Path(directory))
        os.environ['KF_WORKBENCH_ACCESS'] = 'read-only'
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(NoBusinessCalls()))
        print(f'http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
