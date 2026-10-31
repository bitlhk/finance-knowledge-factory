"""Explicit operator-pinned consumption entrypoint; legacy H1a CLIs stay fixed."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import signal
import sys
import threading

from m2.harness_runtime import Runtime, handler as query_handler
from m2.host_leases import HostLeases
from m2.history_runtime import HistoryRuntime, SCHEMA_SHA256 as HISTORY_SHA
from m2.history_service import HistoryServer, handler as history_handler
from m2.process_support import record, code_identity
from m2.runtime_protocol import load_binding, CONTRACT_SHA256
from m2.runtime_service import IsolatedServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('query', 'history'), required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--private-config', type=Path)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path, required=True)
    args = parser.parse_args()
    if (not args.database.is_file() or args.database.is_symlink()
            or args.binding.is_symlink() or not args.binding.is_file()
            or not 0 <= args.port <= 65535 or args.port in (61353, 61358, 61360)):
        parser.error('Explicit trusted binding, isolated database and unreserved port required')
    binding = load_binding(args.binding)
    outbound_attempts = 0
    query_session = None
    if args.mode == 'query':
        if args.private_config is None:
            parser.error('Query requires an existing private upstream configuration')
        from m2.ragflow import RagflowQuerySession
        query_session = RagflowQuerySession(
            args.private_config / 'local-credentials.json', args.private_config / 'http-setup.json')
        runtime = Runtime(args.database, HostLeases(args.authority), query_session, binding=binding)
        server = IsolatedServer(('127.0.0.1', args.port), query_handler(runtime))
    else:
        if args.private_config is not None:
            parser.error('History does not accept upstream configuration')
        def no_outbound(event, _):
            nonlocal outbound_attempts
            if event in ('socket.connect', 'socket.getaddrinfo'):
                outbound_attempts += 1
                raise PermissionError('HISTORY_OUTBOUND_DISABLED')
        sys.addaudithook(no_outbound)
        runtime = HistoryRuntime(args.database, args.authority,
            product=binding['productId'], manifest=binding['manifest'])
        server = HistoryServer(('127.0.0.1', args.port), history_handler(runtime))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    metadata = {'state': 'LISTENING_HOST_AUTH_REQUIRED', 'mode': args.mode,
        'host': '127.0.0.1', 'port': server.server_port, 'binding': binding,
        'bindingFileDigest': sha256(args.binding.read_bytes()).hexdigest(),
        'schemaSha256': CONTRACT_SHA256 if args.mode == 'query' else HISTORY_SHA,
        'codeIdentity': code_identity()}
    ready = False
    try:
        record(args.ready_file, metadata)
        ready = True
        print(json.dumps(metadata), flush=True)
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        if query_session is not None:
            query_session.close()
        if ready:
            stopped = {**metadata, 'state': 'STOPPED_WORKERS_JOINED'}
            if args.mode == 'history':
                stopped['outboundAttempts'] = outbound_attempts
            record(args.ready_file.with_suffix('.stopped.json'), stopped)


if __name__ == '__main__':
    main()
