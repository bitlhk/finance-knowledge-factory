"""Independent loopback metadata service; no query, publish or grant endpoint."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import threading

from knowledge_core.contracts import Rejected
from m2.history_runtime import decode
from m2.product_discovery import DiscoveryLeases, DiscoveryRuntime, ERRORS, MAX_RESPONSE
from m2.product_release import SCHEMA_SHA256
from m2.process_support import code_identity, record


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, raw):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def refuse(self, error):
            status = ERRORS.get(error, 503)
            self.send(status, json.dumps({'code': status, 'error': error}).encode())

        def do_GET(self):
            self.refuse('DISCOVERY_REQUEST_INVALID')

        def do_POST(self):
            try:
                if self.path != '/products/discover':
                    raise ValueError()
                auth = self.headers.get('Authorization', '')
                if len(self.headers.get_all('Authorization', [])) != 1 or not auth.startswith('Bearer '):
                    raise Rejected('DISCOVERY_AUTH_REQUIRED')
                runtime.lease(auth[7:])
                if (self.headers.get('Transfer-Encoding') is not None
                        or len(self.headers.get_all('Content-Length', [])) != 1
                        or len(self.headers.get_all('Content-Type', [])) != 1
                        or self.headers.get_content_type() != 'application/json'):
                    raise ValueError()
                size = int(self.headers['Content-Length'])
                if not 0 < size <= 16384:
                    raise ValueError()
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError()
                result = runtime.discover(auth[7:], decode(raw))
                if len(result) > MAX_RESPONSE:
                    raise Rejected('DISCOVERY_RESPONSE_LIMIT')
                self.send(200, result)
            except Rejected as exc:
                self.refuse(exc.code if exc.code in ERRORS else 'DISCOVERY_UNAVAILABLE')
            except (ValueError, TypeError, UnicodeError, RecursionError):
                self.refuse('DISCOVERY_REQUEST_INVALID')
            except Exception:
                self.refuse('DISCOVERY_UNAVAILABLE')
    return Handler


class DiscoveryServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, request_handler):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, request_handler)

    def process_request(self, request, client_address):
        request.settimeout(5)
        if not self.slots.acquire(blocking=False):
            raw = b'{"code":503,"error":"DISCOVERY_UNAVAILABLE"}'
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--connection-ref', required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path, required=True)
    args = parser.parse_args()
    if (not args.database.is_file() or args.database.is_symlink()
            or not 0 <= args.port <= 65535 or args.port in (61353, 61358, 61360)):
        parser.error('Existing isolated database and unreserved port required')
    runtime = DiscoveryRuntime(args.database, DiscoveryLeases(args.authority), args.connection_ref)
    server = DiscoveryServer(('127.0.0.1', args.port), handler(runtime))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    metadata = {'state': 'LISTENING_HOST_DISCOVERY_AUTH_REQUIRED', 'host': '127.0.0.1',
        'port': server.server_port, 'schemaSha256': SCHEMA_SHA256, 'codeIdentity': code_identity(),
        'connectionRef': args.connection_ref}
    ready = False
    try:
        record(args.ready_file, metadata)
        ready = True
        print(json.dumps(metadata), flush=True)
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        if ready:
            record(args.ready_file.with_suffix('.stopped.json'), {**metadata, 'state': 'STOPPED_WORKERS_JOINED'})


if __name__ == '__main__':
    main()
