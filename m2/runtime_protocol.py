"""Wire contracts only; no identity issuance, permissions or publication logic."""
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from knowledge_core.contracts import Rejected, strict_date

DIRECTORY = Path(__file__).resolve().parents[1] / 'contracts/runtime'
SCHEMA_BYTES = (DIRECTORY / 'knowledge-runtime-v0.1.schema.json').read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)
CONTRACT_SHA256 = sha256(SCHEMA_BYTES).hexdigest()


def validate_wire(kind, body):
    validator = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/' + kind})
    if not validator.is_valid(body):
        raise Rejected('KNOWLEDGE_QUERY_INVALID' if kind.endswith('Request') else 'KNOWLEDGE_RESPONSE_INVALID')
    if kind == 'queryRequest':
        strict_date(body['businessDate'])


def load_binding(path):
    value = json.loads(Path(path).read_bytes())
    if (set(value) != {'schemaVersion', 'productId', 'manifest', 'productionBaseline'}
            or value['schemaVersion'] != 'knowledge-runtime-binding.v0.1'):
        raise ValueError('RUNTIME_BINDING_INVALID')
    for key, definition in [('productId', 'id'), ('manifest', 'hash')]:
        Draft202012Validator(SCHEMA['$defs'][definition]).validate(value[key])
    return value
