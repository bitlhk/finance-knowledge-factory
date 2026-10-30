import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from knowledge_core.contracts import SCHEMAS, Rejected, canonical, digest, validate


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_exported_contracts_are_valid_and_match_registry(name):
    Draft202012Validator.check_schema(SCHEMAS[name])
    stored = json.loads((Path(__file__).parents[1] / "contracts" / f"{name}-v0.1.schema.json").read_text())
    assert stored == SCHEMAS[name]


def test_hash_is_order_independent_not_js_coercion():
    assert digest({"a": 1, "b": True}) == digest({"b": True, "a": 1})
    assert digest({"a": True}) != digest({"a": 1})
    with pytest.raises(Rejected, match="FLOAT_NOT_ALLOWED"):
        canonical({"amount": 0.1})


def test_unknown_contract_and_properties_rejected():
    with pytest.raises(Rejected, match="UNKNOWN_CONTRACT"):
        validate("unknown", {})
    with pytest.raises(Rejected, match="SCHEMA_INVALID"):
        validate("active-policy", {"schemaVersion": "active-policy.v0.1", "revision": 1, "grants": [], "execute": "shell"})
