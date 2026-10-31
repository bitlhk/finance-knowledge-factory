"""Runtime fixture built through Core, independently of UI or rule experiments."""
from types import SimpleNamespace
import json
from urllib import request, error

from knowledge_core.documents import DocumentCore
from m2.pipeline import produce
from m2.synthetic_context import AUTHOR, READER, CONTEXT, SCOPE, CASES
from tests.test_m2_documents import ControlledClient, RAW
from m2.runtime_protocol import validate_wire


def http(base, path, token, body):
    headers = {'Content-Type':'application/json'}
    if token is not None: headers['Authorization'] = 'Bearer '+token
    req = request.Request(base+path, json.dumps(body).encode(), headers=headers)
    try:
        response = request.urlopen(req, timeout=90)
    except error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(262145)
        assert len(raw) <= 262144
        result = json.loads(raw)
        validate_wire('errorResponse' if response.status != 200 else
                      'queryResponse' if path == '/query' else 'sessionResponse', result)
        return response.status, result


def make(tmp_path):
    database = tmp_path / 'runtime.sqlite'
    core = DocumentCore(database)
    client = ControlledClient()
    product = 'runtime-test'
    grants = []
    for principal in (AUTHOR.principal, READER.principal):
        grants += [{'principal': principal, 'resource': 'product:'+product, 'actions': ['consume', 'history']},
                   {'principal': principal, 'resource': 'source:'+product+'-source', 'actions': ['source_read']}]
    try:
        core.set_policy(AUTHOR, {'schemaVersion':'active-policy.v0.1', 'revision':1, 'grants':grants}, 0)
        data = produce(core, AUTHOR, product, 1, RAW, SCOPE, CASES, [READER.principal], client)
        core.activate_source(AUTHOR, data['sourceDigest'], '2026-01-01')
        validation = core.validate_document(AUTHOR, data['candidateDigest'], client)
        approval = core.approve_document(AUTHOR, data['candidateDigest'], validation, 'Isolated Runtime test only')
        manifest = core.publish_document(AUTHOR, data['candidateDigest'], validation, approval, 1)
        core.bind_document(AUTHOR, manifest, 0)
    finally:
        core.close()
    service = SimpleNamespace(database=database, core=lambda: DocumentCore(database), close=lambda: None)
    return service, client, {'id':product}, {'manifestDigest':manifest}
