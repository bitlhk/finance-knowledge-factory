"""Single-operator loopback preview. Not a multi-tenant or production service."""
import argparse
import fcntl
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from knowledge_core.contracts import Rejected
from web_preview.server import assets as preview_assets, BASELINE_SHA
from web_production.engine import Production, ROOT, SAMPLE


def handler(service):
    css = preview_assets()['/style.css'][1]
    files = {'/': ('text/html; charset=utf-8', (ROOT / 'web_production/index.html').read_bytes()),
             '/app.js': ('text/javascript; charset=utf-8', (ROOT / 'web_production/app.js').read_bytes()),
             '/style.css': ('text/css; charset=utf-8', css + (ROOT / 'web_production/style.css').read_bytes())}
    version = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True))
    test_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, payload, mime='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def trusted_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.trusted_host():
                return self.respond(403, {'error': 'LOOPBACK_HOST_REQUIRED'})
            path = urlsplit(self.path).path
            try:
                if path in files:
                    mime, body = files[path]
                    return self.respond(200, body, mime)
                if path == '/api/state':
                    return self.respond(200, {**service.snapshot(), 'commit': version, 'dirty': dirty,
                        'prototypeSha256': BASELINE_SHA, 'version': 'Web Preview V0.2'})
                if path.startswith('/api/runs/'):
                    return self.respond(200, service.get(path.removeprefix('/api/runs/')))
                return self.respond(404, {'error': 'NOT_FOUND'})
            except Rejected as exc:
                return self.respond(409, {'error': exc.code})

        do_HEAD = do_GET

        def do_POST(self):
            host = self.headers.get('Host')
            if not self.trusted_host() or self.headers.get('Origin') != 'http://' + host:
                return self.respond(403, {'error': 'SAME_ORIGIN_REQUIRED'})
            if self.headers.get('Content-Type') != 'application/json':
                return self.respond(415, {'error': 'JSON_REQUIRED'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    return self.respond(413, {'error': 'BODY_SIZE_LIMIT'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise Rejected('OBJECT_REQUIRED')
                path = urlsplit(self.path).path
                if path == '/api/sample':
                    result = service.source('个人贷款管理办法 · 公开制度样例', SAMPLE.read_text())
                elif path == '/api/sources' and set(data) == {'title', 'html'}:
                    result = service.source(data['title'], data['html'])
                elif path == '/api/runs':
                    result = service.submit(data)
                elif path == '/api/search' and set(data) == {'runId', 'query'}:
                    result = service.search(data['runId'], data['query'])
                elif path == '/api/rule-test' and set(data) == {'runId', 'clause', 'ruleId', 'inputs'}:
                    if not test_lock.acquire(blocking=False):
                        raise Rejected('RULE_TEST_BUSY')
                    try:
                        result = service.rule_test(data['runId'], data['clause'], data['ruleId'], data['inputs'])
                    finally:
                        test_lock.release()
                else:
                    return self.respond(404, {'error': 'NOT_FOUND'})
                return self.respond(200, result)
            except Rejected as exc:
                return self.respond(409, {'error': exc.code})
            except (ValueError, UnicodeError, TypeError, KeyError):
                return self.respond(400, {'error': 'INVALID_REQUEST'})
            except Exception:
                return self.respond(500, {'error': 'REQUEST_FAILED'})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=61352)
    parser.add_argument('--state', required=True)
    args = parser.parse_args()
    from pathlib import Path
    state = Path(args.state).resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / '.server.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        service = Production(state)
        http = ThreadingHTTPServer(('127.0.0.1', args.port), handler(service))
        (state / 'server.pid').write_text(str(os.getpid()))
        print(f'Candidate-only preview: http://127.0.0.1:{args.port}/', flush=True)
        try:
            http.serve_forever()
        finally:
            http.server_close()
            service.close()


if __name__ == '__main__':
    main()
