"""Isolated consumption server. Host supplies authority; this process only reads it."""
import argparse
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import tempfile

from m2.harness_runtime import Runtime, handler
from m2.host_leases import HostLeases, private_bytes
from m2.ragflow import Ragflow
from m2.runtime_protocol import CONTRACT_SHA256, DIRECTORY, load_binding


class IsolatedServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 8

    def __init__(self, address, handler_class):
        self.capacity = threading.BoundedSemaphore(8)
        super().__init__(address, handler_class)

    def process_request(self, connection, address):
        connection.settimeout(5)
        if not self.capacity.acquire(blocking=False):
            try:
                body = b'{"code":503,"error":"KNOWLEDGE_BUSY"}'
                connection.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                    + b'Cache-Control: no-store\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
            finally:
                self.shutdown_request(connection)
            return
        try:
            super().process_request(connection, address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, connection, address):
        try:
            super().process_request_thread(connection, address)
        finally:
            self.capacity.release()

    def handle_error(self, *_):
        pass  # Never emit headers, credentials or request bodies in tracebacks.


def record(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.runtime-record-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic visibility and no overwrite, including symlinks.
    finally:
        os.unlink(temporary)


def code_identity():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(['git','rev-parse','HEAD'],cwd=root,check=True,
            capture_output=True,text=True,timeout=5).stdout.strip()
        status = subprocess.run(['git','status','--porcelain'],cwd=root,check=True,
            capture_output=True,text=True,timeout=5).stdout
        return {'commit':commit,'dirty':bool(status)}
    except (OSError,subprocess.SubprocessError):
        return {'commit':None,'dirty':None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--authority', type=Path, required=True, help='Host-owned private policy; read only')
    parser.add_argument('--private-config', type=Path, required=True, help='Existing RAGFlow connection configuration')
    parser.add_argument('--binding', type=Path, default=DIRECTORY/'h1a-binding.json')
    parser.add_argument('--port', type=int, default=61357)
    parser.add_argument('--ready-file', type=Path, required=True, help='New private readiness file, never overwrite')
    args = parser.parse_args()
    private_bytes(args.authority)
    if not args.database.is_file() or args.database.is_symlink():
        raise ValueError('EXISTING_CORE_REQUIRED')
    if not 0 <= args.port <= 65535 or args.port == 61353:
        raise ValueError('ISOLATED_PORT_REQUIRED')
    binding = load_binding(args.binding)
    # The H1a instance is pinned independently of mutable Host policy files.
    if binding != load_binding(DIRECTORY/'h1a-binding.json'):
        raise ValueError('H1A_FIXED_BINDING_REQUIRED')
    runtime = Runtime(args.database, HostLeases(args.authority), lambda: Ragflow(
        args.private_config/'local-credentials.json', args.private_config/'http-setup.json'), binding=binding)
    server = IsolatedServer(('127.0.0.1', args.port), handler(runtime))
    metadata = {'schemaVersion':'knowledge-runtime-process.v0.1', 'pid':os.getpid(),
        'host':'127.0.0.1', 'port':server.server_port, 'binding':binding,
        'codeIdentity':code_identity(),
        'contractSha256':CONTRACT_SHA256, 'authority':'HOST_OWNED_READ_ONLY',
        'implementation':{name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('runtime_service.py','host_leases.py','harness_runtime.py','runtime_protocol.py')}}
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    previous = {sig:signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    ready = False
    try:
        record(args.ready_file, {**metadata, 'status':'LISTENING_NOT_AUTHORIZATION_ACCEPTANCE'})
        ready = True
        print(json.dumps({'status':'LISTENING','port':server.server_port,'contractSha256':CONTRACT_SHA256}), flush=True)
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        for sig, action in previous.items(): signal.signal(sig, action)
        if ready:
            record(args.ready_file.with_suffix('.stopped.json'), {**metadata,
                'status':'SERVER_CLOSED_WORKERS_JOINED', 'scope':'ONLY_THIS_RUNTIME_HTTP_PROCESS'})


if __name__ == '__main__':
    main()
