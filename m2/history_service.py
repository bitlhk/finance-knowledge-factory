"""Loopback-only, history-only HTTP process. No upstream client configuration."""
import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import sys
import threading

from knowledge_core.contracts import Rejected
from m2.history_runtime import HistoryRuntime, MAX_REQUEST, MAX_RESPONSE, ERRORS, decode, SCHEMA_SHA256
from m2.process_support import code_identity, record
from m2.runtime_protocol import DIRECTORY, load_binding


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, raw):
            if len(raw) > MAX_RESPONSE:
                status, raw = 413, b'{"code":413,"error":"HISTORY_RESPONSE_LIMIT"}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def refuse(self, code):
            status = ERRORS[code]
            self.respond(status, json.dumps({'code': status, 'error': code}).encode())

        def do_GET(self):
            self.refuse('HISTORY_REQUEST_INVALID')

        def do_POST(self):
            try:
                if self.path != '/history/read':
                    raise ValueError()
                if len(self.headers.get_all('Authorization', [])) != 1:
                    raise Rejected('HISTORY_AUTH_REQUIRED')
                auth = self.headers['Authorization']
                if not auth.startswith('Bearer '):
                    raise Rejected('HISTORY_AUTH_REQUIRED')
                runtime.lease(auth[7:])
                if (self.headers.get('Transfer-Encoding') is not None
                        or len(self.headers.get_all('Content-Length', [])) != 1
                        or len(self.headers.get_all('Content-Type', [])) != 1
                        or self.headers.get_content_type() != 'application/json'):
                    raise ValueError()
                size = int(self.headers['Content-Length'])
                if not 0 < size <= MAX_REQUEST:
                    raise ValueError()
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError()
                self.respond(200, runtime.read(auth[7:], decode(raw)))
            except Rejected as exc:
                self.refuse(exc.code if exc.code in ERRORS else 'HISTORY_UNAVAILABLE')
            except (ValueError, TypeError, UnicodeError, RecursionError):
                self.refuse('HISTORY_REQUEST_INVALID')
            except Exception:
                self.refuse('HISTORY_UNAVAILABLE')
    return Handler


class HistoryServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, request_handler):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, request_handler)

    def process_request(self, request, client_address):
        request.settimeout(5)
        if not self.slots.acquire(blocking=False):
            raw = b'{"code":503,"error":"HISTORY_UNAVAILABLE"}'
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                    b'Cache-Control: no-store\r\nConnection: close\r\nContent-Length: ' + str(len(raw)).encode() + b'\r\n\r\n' + raw)
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--product', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--port', type=int, default=61359)
    parser.add_argument('--ready-file', type=Path, required=True, help='New process evidence file, never overwritten')
    args = parser.parse_args()
    if (args.port in (61353, 61358) or not 0 <= args.port <= 65535
            or not args.database.is_file() or args.database.is_symlink()):
        parser.error('Existing database and unreserved port required')
    fixed = load_binding(DIRECTORY / 'h1a-binding.json')
    if (args.product, args.manifest) != (fixed['productId'], fixed['manifest']):
        parser.error('H1a fixed product and Manifest required')
    runtime = HistoryRuntime(args.database, args.authority, product=args.product, manifest=args.manifest)
    outbound_attempts = 0

    def no_outbound(event, _):
        nonlocal outbound_attempts
        if event in ('socket.connect', 'socket.getaddrinfo'):
            outbound_attempts += 1
            raise PermissionError('HISTORY_OUTBOUND_DISABLED')
    sys.addaudithook(no_outbound)
    server = HistoryServer(('127.0.0.1', args.port), handler(runtime))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    # Missing Host policy is fail-closed and can be provisioned later by Harness.
    metadata = {'state': 'LISTENING_HOST_AUTH_REQUIRED', 'host': '127.0.0.1', 'port': server.server_port,
        'pid': os.getpid(), 'schemaSha256': SCHEMA_SHA256, 'outboundDisabled': True,
        'binding': {'productId': args.product, 'manifest': args.manifest}, 'codeIdentity': code_identity(),
        'implementation': {name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ('history_service.py', 'history_runtime.py')}}
    ready = False
    try:
        record(args.ready_file, metadata)
        ready = True
        print(json.dumps(metadata), flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        stopped = {**metadata, 'state': 'STOPPED_WORKERS_JOINED', 'outboundAttempts': outbound_attempts}
        if ready:
            record(args.ready_file.with_suffix('.stopped.json'), stopped)
        print(json.dumps(stopped), flush=True)


if __name__ == '__main__':
    main()
