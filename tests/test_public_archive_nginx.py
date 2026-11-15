"""Exercise deploy snippets using isolated nginx, never reload the system proxy."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import pytest


def test_per_ip_budget_ignores_spoofed_headers_and_logs_no_query(tmp_path):
    nginx = shutil.which('nginx')
    if not nginx:
        pytest.skip('nginx binary required for isolated proxy integration')

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parents[1] / 'deploy/nginx'
    http_config = (root / 'public-archive-http.conf').read_text()
    server_config = (root / 'public-archive-server.conf').read_text().replace(
        '/var/log/nginx/', str(tmp_path) + '/')
    config = tmp_path / 'nginx.conf'
    config.write_text(f'''
pid {tmp_path}/nginx.pid;
error_log {tmp_path}/master-error.log warn;
events {{ worker_connections 64; }}
http {{
    access_log off;
    {http_config}
    server {{
        listen 127.0.0.1:{port};
        {server_config}
        location / {{ proxy_pass http://127.0.0.1:{upstream.server_port}; }}
    }}
}}
''')
    process = None

    def get(path, ip='127.0.0.1', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2,
                                                source_address=(ip, 0))
        try:
            connection.request('GET', path, headers=headers or {})
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    try:
        subprocess.run([nginx, '-t', '-p', str(tmp_path), '-c', str(config)],
                       check=True, capture_output=True)
        process = subprocess.Popen([nginx, '-p', str(tmp_path), '-c', str(config),
                                    '-g', 'daemon off;'], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if get('/api/state') == 200:
                    break
            except OSError:
                time.sleep(.02)
        else:
            pytest.fail('Isolated proxy did not become ready')
        path = '/api/published-products/000051/pages?page=1&query=private-test-query'
        statuses = [get(path) for _ in range(15)]
        assert 200 in statuses and 429 in statuses
        assert get(path, headers={'X-Forwarded-For': '192.0.2.55'}) == 429
        assert get(path, ip='127.0.0.2') == 200
        assert get('/api/state') == 200
        assert get('/workbench.js') == 200
        assert get('/') == 200
    finally:
        if process:
            process.terminate()
            process.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        thread.join()
    logs = '\n'.join(p.read_text() for p in tmp_path.glob('*.log'))
    assert 'archive_read_limited' in logs
    assert 'private-test-query' not in logs
    assert 'X-Forwarded-For' not in logs
