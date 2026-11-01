"""Local Host-issued leases for an isolated installed Agent, not production IAM.

The private authority policy is prepared by the operator, never by a tool or
browser. Issuing a session does not change Core permissions or source activation.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat

from knowledge_core.core import Actor, BusinessContext
from knowledge_core.contracts import Rejected
from m2.harness_runtime import Lease, Runtime, handler, _unique
from m2.ragflow import Ragflow


def private_bytes(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
            raise Rejected('PRIVATE_AUTHORITY_REQUIRED')
        raw = stream.read(16385)
        if len(raw) > 16384:
            raise Rejected('PRIVATE_AUTHORITY_REQUIRED')
        return raw


class HostLeases:
    def __init__(self, policy):
        self.policy = Path(policy)

    def __call__(self, token):
        try:
            raw = private_bytes(self.policy)
            config = json.loads(raw, object_pairs_hook=_unique)
            if config['schemaVersion'] != 'knowledge-host-authority.v0.1' or config['enabled'] is not True:
                raise ValueError()
            expiry = datetime.fromisoformat(config['expiresAt'].replace('Z', '+00:00'))
            if expiry <= datetime.now(timezone.utc):
                raise ValueError()
            directory = Path(config['leaseDirectory'])
            info = directory.lstat()
            if not directory.is_absolute() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
                raise ValueError()
            lease = json.loads(private_bytes(directory / (sha256(token.encode()).hexdigest()+'.json')), object_pairs_hook=_unique)
            if (lease['schemaVersion'] != 'knowledge-host-lease.v0.1'
                    or lease['policyDigest'] != sha256(raw).hexdigest() or lease['ownerRef'] != config['ownerRef']
                    or not lease['instanceId'] or not lease['sessionRef']):
                raise ValueError()
            end = datetime.fromisoformat(lease['expiresAt'].replace('Z', '+00:00'))
            if end > expiry:
                raise ValueError()
            result = Lease(Actor(config['tenant'],config['principalId'],config['authority']),
                BusinessContext(**config['context']),config['subjectRef'],lease['sessionRef'],
                config['productId'],config['manifest'],end)
            result.check()
            return result
        except (KeyError, TypeError, ValueError, OSError, Rejected):
            return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--authority',type=Path,required=True)
    parser.add_argument('--private-config',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    args = parser.parse_args()
    private_bytes(args.authority)
    if not args.database.is_file():
        raise ValueError('EXISTING_CORE_REQUIRED')
    runtime = Runtime(args.database,HostLeases(args.authority),lambda:Ragflow(
        args.private_config/'local-credentials.json',args.private_config/'http-setup.json'))
    server = ThreadingHTTPServer(('127.0.0.1',args.port),handler(runtime))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
