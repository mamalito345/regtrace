from pathlib import Path

import pytest

from regtrace.api import verify_repository
from regtrace.matcher import (
    PolicyBindings,
    TechnicalBinding,
)
from regtrace.models.constraint import (
    Action,
    Condition,
    Constraint,
    PolicySpec,
)
from regtrace.models.verification import (
    ConstraintVerdict,
)
from regtrace.repository import (
    RepositoryAnalysisError,
    RepositoryAnalyzer,
)


def _policy() -> PolicySpec:
    return PolicySpec(
        policy_id="P-TEST",
        policy_title="Repository test",
        constraints=[
            Constraint(
                id="C-1",
                condition=Condition(
                    name="explicit_consent",
                ),
                action=Action(
                    name="external_export",
                ),
            )
        ],
    )


def _bindings() -> PolicyBindings:
    return PolicyBindings(
        bindings=[
            TechnicalBinding(
                concept="explicit_consent",
                aliases=[
                    "customer.export_consent",
                ],
            ),
            TechnicalBinding(
                concept="external_export",
                aliases=[
                    "crm.send",
                ],
            ),
        ]
    )


def _write(
    root: Path,
    relative: str,
    source: str,
) -> None:
    path = root / relative
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        source,
        encoding="utf-8",
    )


def test_repository_analyzer_discovers_nested_python_files(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "app.py",
        "x = 1\n",
    )

    _write(
        tmp_path,
        "service/export.py",
        "y = 2\n",
    )

    _write(
        tmp_path,
        "README.md",
        "ignored\n",
    )

    analysis = RepositoryAnalyzer().analyze(
        tmp_path
    )

    assert analysis.analyzed_files == (
        "app.py",
        "service/export.py",
    )

    assert analysis.issues == ()


def test_repository_analyzer_ignores_environment_directories(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "app.py",
        "x = 1\n",
    )

    _write(
        tmp_path,
        ".venv/lib/bad.py",
        "this is not python !!!\n",
    )

    analysis = RepositoryAnalyzer().analyze(
        tmp_path
    )

    assert analysis.analyzed_files == (
        "app.py",
    )

    assert analysis.issues == ()


def test_repository_with_unguarded_action_fails(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "customer_export.py",
        """
def export_customer(customer):
    crm.send(customer.email)
""",
    )

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.FAIL
    )

    assert (
        result.results[0].counterexample
        is not None
    )

    assert (
        result.results[0]
        .counterexample
        .filename
        == "customer_export.py"
    )


def test_repository_with_guarded_action_passes(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "customer_export.py",
        """
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
""",
    )

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.PASS
    )


def test_guarded_and_unguarded_calls_across_files_fail(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "safe_export.py",
        """
def export_safe(customer):
    if customer.export_consent:
        crm.send(customer.email)
""",
    )

    _write(
        tmp_path,
        "unsafe_export.py",
        """
def export_unsafe(customer):
    crm.send(customer.phone)
""",
    )

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.FAIL
    )

    assert (
        result.results[0].counterexample
        is not None
    )

    assert (
        result.results[0]
        .counterexample
        .filename
        == "unsafe_export.py"
    )


def test_action_absent_in_repository_is_unknown(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "customer.py",
        """
def get_customer(customer):
    return customer.email
""",
    )

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.UNKNOWN
    )


def test_parse_error_downgrades_pass_to_unknown(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "safe_export.py",
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

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.UNKNOWN
    )

    assert "broken.py" in (
        result.overall_reason
    )


def test_known_fail_dominates_repository_parse_error(
    tmp_path: Path,
):
    _write(
        tmp_path,
        "unsafe_export.py",
        """
def export_customer(customer):
    crm.send(customer.email)
""",
    )

    _write(
        tmp_path,
        "broken.py",
        "def broken(:\n",
    )

    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.FAIL
    )

    assert "Known violation found" in (
        result.overall_reason
    )


def test_empty_repository_is_unknown(
    tmp_path: Path,
):
    result = verify_repository(
        tmp_path,
        _policy(),
        _bindings(),
    )

    assert result.overall == (
        ConstraintVerdict.UNKNOWN
    )


def test_missing_repository_raises_clear_error(
    tmp_path: Path,
):
    missing = (
        tmp_path
        / "does-not-exist"
    )

    with pytest.raises(
        RepositoryAnalysisError
    ):
        RepositoryAnalyzer().analyze(
            missing
        )