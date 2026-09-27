import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from regtrace.api import verify_with_text
from regtrace.llm import LLMProvider
from regtrace.models.constraint import Constraint
from regtrace.models.verification import ConstraintVerdict


class QueueProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(
        self,
        system: str,
        user: str,
    ) -> str:
        if not self._responses:
            raise AssertionError(
                "No fake LLM response left"
            )

        return self._responses.pop(0)


def _policy_json() -> str:
    return json.dumps(
        {
            "policy_id": "P-DEMO",
            "policy_title": "Consent before export",
            "constraints": [
                {
                    "id": "C-1",
                    "type": "require_before",
                    "severity": "required",
                    "condition": {
                        "name": "explicit_consent"
                    },
                    "action": {
                        "name": "external_export"
                    },
                }
            ],
        }
    )


def _write(
    path: Path,
    relative: str,
    source: str,
) -> None:
    target = path / relative

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        source,
        encoding="utf-8",
    )


def test_constraint_rejects_unsupported_type() -> None:
    with pytest.raises(ValidationError):
        Constraint.model_validate(
            {
                "id": "C-1",
                "type": "forbid",
                "condition": {
                    "name": "x"
                },
                "action": {
                    "name": "y"
                },
            }
        )


def test_verify_with_text_missing_binding_is_unknown(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "export.py",
        """
def export_customer(customer):
    if customer.export_consent:
        audit.log(customer.email)

    crm.send(customer.email)
""",
    )

    provider = QueueProvider(
        [
            _policy_json(),
            json.dumps(
                {
                    "explicit_consent": [],
                    "external_export": [
                        "crm.send"
                    ],
                }
            ),
        ]
    )

    result = verify_with_text(
        tmp_path,
        "Export only after explicit consent.",
        "Export customer to CRM.",
        provider,
    )

    assert (
        result.overall
        == ConstraintVerdict.UNKNOWN
    )

    assert (
        "explicit_consent"
        in result.overall_reason
    )


def test_verify_with_text_parse_error_downgrades_pass(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "safe.py",
        """
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
""",
    )

    _write(
        tmp_path,
        "broken.py",
        "def broken(:\n",
    )

    provider = QueueProvider(
        [
            _policy_json(),
            json.dumps(
                {
                    "explicit_consent": [
                        "customer.export_consent"
                    ],
                    "external_export": [
                        "crm.send"
                    ],
                }
            ),
        ]
    )

    result = verify_with_text(
        tmp_path,
        "Export only after explicit consent.",
        "Export customer to CRM.",
        provider,
    )

    assert (
        result.overall
        == ConstraintVerdict.UNKNOWN
    )

    assert (
        "broken.py"
        in result.overall_reason
    )


def test_verify_with_text_unguarded_action_fails(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "export.py",
        """
def export_customer(customer):
    if customer.export_consent:
        audit.log(customer.email)

    crm.send(customer.email)
""",
    )

    provider = QueueProvider(
        [
            _policy_json(),
            json.dumps(
                {
                    "explicit_consent": [
                        "customer.export_consent"
                    ],
                    "external_export": [
                        "crm.send"
                    ],
                }
            ),
        ]
    )

    result = verify_with_text(
        tmp_path,
        "Export only after explicit consent.",
        "Export customer to CRM.",
        provider,
    )

    assert (
        result.overall
        == ConstraintVerdict.FAIL
    )

    counterexample = (
        result.results[0]
        .counterexample
    )

    assert counterexample is not None

    assert (
        counterexample.code_identifier
        == "crm.send"
    )

    assert (
        counterexample.condition_alias
        is None
    )


def test_verify_with_text_guarded_action_passes(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "export.py",
        """
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
""",
    )

    provider = QueueProvider(
        [
            _policy_json(),
            json.dumps(
                {
                    "explicit_consent": [
                        "customer.export_consent"
                    ],
                    "external_export": [
                        "crm.send"
                    ],
                }
            ),
        ]
    )

    result = verify_with_text(
        tmp_path,
        "Export only after explicit consent.",
        "Export customer to CRM.",
        provider,
    )

    assert (
        result.overall
        == ConstraintVerdict.PASS
    )