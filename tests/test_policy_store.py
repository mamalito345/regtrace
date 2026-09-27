"""
tests/test_policy_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for PolicyStore.
"""
import json
import tempfile
from pathlib import Path

import pytest

from regtrace.policy_store import PolicyStore, PolicyLoadError
from regtrace.models.constraint import PolicySpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SPEC = {
    "policy_id": "TEST-001",
    "policy_title": "Test policy",
    "constraints": [
        {
            "id": "C-T-001",
            "type": "require_before",
            "severity": "required",
            "condition": {"name": "some_condition"},
            "action": {"name": "some_action"},
        }
    ],
}

SECOND_SPEC = {
    "policy_id": "TEST-002",
    "policy_title": "Second policy",
    "constraints": [
        {
            "id": "C-T-002",
            "type": "require_before",
            "severity": "required",
            "condition": {"name": "other_condition"},
            "action": {"name": "other_action"},
        }
    ],
}


def write_json(directory: Path, filename: str, data: dict) -> Path:
    p = directory / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Valid policy JSON loads
# ---------------------------------------------------------------------------

def test_load_valid_file():
    with tempfile.TemporaryDirectory() as d:
        f = write_json(Path(d), "TEST-001.json", VALID_SPEC)
        store = PolicyStore()
        spec = store.load_file(f)
        assert isinstance(spec, PolicySpec)
        assert spec.policy_id == "TEST-001"
        assert len(spec.constraints) == 1


# ---------------------------------------------------------------------------
# 2. Malformed JSON fails clearly
# ---------------------------------------------------------------------------

def test_bad_json_raises_policy_load_error():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.json"
        p.write_text("{ not valid json }", encoding="utf-8")
        with pytest.raises(PolicyLoadError, match="Invalid JSON"):
            PolicyStore().load_file(p)


def test_missing_required_field_raises_policy_load_error():
    """Missing `constraints` field should fail validation."""
    bad = {"policy_id": "X"}  # missing constraints
    with tempfile.TemporaryDirectory() as d:
        f = write_json(Path(d), "bad.json", bad)
        with pytest.raises(PolicyLoadError, match="Schema error"):
            PolicyStore().load_file(f)


def test_missing_file_raises_policy_load_error():
    with pytest.raises(PolicyLoadError, match="not found"):
        PolicyStore().load_file("/nonexistent/path/policy.json")


# ---------------------------------------------------------------------------
# 3. Multiple policies load from a directory
# ---------------------------------------------------------------------------

def test_load_directory():
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        write_json(dp, "TEST-001.json", VALID_SPEC)
        write_json(dp, "TEST-002.json", SECOND_SPEC)
        store = PolicyStore()
        specs = store.load_directory(dp)
        assert len(specs) == 2
        ids = {s.policy_id for s in specs}
        assert ids == {"TEST-001", "TEST-002"}


def test_get_loaded_policy():
    with tempfile.TemporaryDirectory() as d:
        f = write_json(Path(d), "TEST-001.json", VALID_SPEC)
        store = PolicyStore()
        store.load_file(f)
        spec = store.get("TEST-001")
        assert spec.policy_id == "TEST-001"


def test_get_missing_policy_raises_key_error():
    store = PolicyStore()
    with pytest.raises(KeyError):
        store.get("DOES-NOT-EXIST")


def test_all_returns_all_loaded():
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        write_json(dp, "TEST-001.json", VALID_SPEC)
        write_json(dp, "TEST-002.json", SECOND_SPEC)
        store = PolicyStore()
        store.load_directory(dp)
        assert len(store.all()) == 2


# ---------------------------------------------------------------------------
# 4. P-001 fixture file loads correctly
# ---------------------------------------------------------------------------

def test_p001_fixture_loads():
    """The committed P-001 JSON must load and validate."""
    store = PolicyStore()
    here = Path(__file__).parent.parent / "regtrace-core" / "policies" / "P-001-consent-export.json"
    if not here.exists():
        pytest.skip("P-001 fixture not present")
    spec = store.load_file(here)
    assert spec.policy_id == "P-001"
    assert len(spec.constraints) >= 1
