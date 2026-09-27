"""
tests/test_evaluator.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for PythonPolicyEvaluator.

The evaluator operates on paired (action, condition) Facts as produced by
PolicyCodeMatcher: for each call site the matcher emits one action Fact
followed immediately by one condition Fact.

Covers:
  - explicit_consent scenarios (privacy domain)
  - manager_approval scenarios (finance domain)

Both domains use the SAME evaluator — proves no hard-coded domain logic.
"""
import pytest

from regtrace.models.constraint import Constraint, Condition, Action, ConstraintSeverity
from regtrace.models.evidence import Evidence, Fact
from regtrace.models.verification import ConstraintVerdict
from regtrace.evaluator import PythonPolicyEvaluator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def evaluator() -> PythonPolicyEvaluator:
    return PythonPolicyEvaluator()


def make_constraint(cid: str, condition: str, action: str,
                    severity: ConstraintSeverity = ConstraintSeverity.REQUIRED) -> Constraint:
    return Constraint(
        id=cid,
        condition=Condition(name=condition),
        action=Action(name=action),
        severity=severity,
    )


def make_evidence(constraint_id: str, facts: list[Fact]) -> Evidence:
    return Evidence(constraint_id=constraint_id, facts=facts)


# ---------------------------------------------------------------------------
# Privacy domain: explicit_consent / external_personal_data_export
# Pairs: action Fact followed by condition Fact (matcher contract)
# ---------------------------------------------------------------------------

CONSENT_CONSTRAINT = make_constraint(
    "C-CONSENT",
    condition="explicit_consent",
    action="external_personal_data_export",
)


def test_consent_true_before_export_passes(evaluator):
    """explicit_consent=true, export occurred → PASS"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(condition_name="explicit_consent", condition_held=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.PASS


def test_consent_false_before_export_fails(evaluator):
    """explicit_consent=false + export occurs → FAIL"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(condition_name="explicit_consent", condition_held=False),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.FAIL


def test_consent_state_unavailable_export_occurs_unknown(evaluator):
    """No consent observation + export occurs → UNKNOWN"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# Finance domain: manager_approval / high_value_refund
# ---------------------------------------------------------------------------

APPROVAL_CONSTRAINT = make_constraint(
    "C-APPROVAL",
    condition="manager_approval",
    action="high_value_refund",
)


def test_manager_approval_true_before_refund_passes(evaluator):
    """manager_approval=true before high_value_refund → PASS"""
    evidence = make_evidence("C-APPROVAL", [
        Fact(action_name="high_value_refund", action_occurred=True),
        Fact(condition_name="manager_approval", condition_held=True),
    ])
    result = evaluator.evaluate(APPROVAL_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.PASS


def test_manager_approval_false_before_refund_fails(evaluator):
    """manager_approval=false + high_value_refund occurs → FAIL"""
    evidence = make_evidence("C-APPROVAL", [
        Fact(action_name="high_value_refund", action_occurred=True),
        Fact(condition_name="manager_approval", condition_held=False),
    ])
    result = evaluator.evaluate(APPROVAL_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.FAIL
    assert result.counterexample is not None
    assert result.counterexample.condition_name == "manager_approval"
    assert result.counterexample.action_name == "high_value_refund"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_action_fact_is_unknown(evaluator):
    """No action observed → UNKNOWN (nothing to evaluate)"""
    evidence = make_evidence("C-CONSENT", [
        Fact(condition_name="explicit_consent", condition_held=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.UNKNOWN


def test_no_ordering_consent_true_only_passes(evaluator):
    """action + condition=true (no seq) → PASS"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(condition_name="explicit_consent", condition_held=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.PASS


def test_no_ordering_consent_false_only_fails(evaluator):
    """action + condition=false (no seq) → FAIL"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(condition_name="explicit_consent", condition_held=False),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.FAIL


def test_multiple_sites_all_guarded_passes(evaluator):
    """Two call sites, both condition=true → PASS"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True, lineno=5),
        Fact(condition_name="explicit_consent", condition_held=True),
        Fact(action_name="external_personal_data_export", action_occurred=True, lineno=10),
        Fact(condition_name="explicit_consent", condition_held=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.PASS


def test_multiple_sites_one_unguarded_fails(evaluator):
    """Two call sites: one guarded, one not → FAIL"""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True, lineno=3),
        Fact(condition_name="explicit_consent", condition_held=True),
        Fact(action_name="external_personal_data_export", action_occurred=True, lineno=7),
        Fact(condition_name="explicit_consent", condition_held=False),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.FAIL


def test_action_before_consent_is_unknown(evaluator):
    """Action present but condition count mismatch (mismatched pairs) → UNKNOWN"""
    # 2 action facts, 1 condition fact — matcher contract violation → UNKNOWN
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(action_name="external_personal_data_export", action_occurred=True),
        Fact(condition_name="explicit_consent", condition_held=True),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.UNKNOWN


def test_recommended_severity_returns_unknown(evaluator):
    """RECOMMENDED constraints are not enforced in MVP → UNKNOWN."""
    c = make_constraint("C-REC", "some_condition", "some_action",
                        severity=ConstraintSeverity.RECOMMENDED)
    evidence = make_evidence("C-REC", [
        Fact(action_name="some_action", action_occurred=True),
        Fact(condition_name="some_condition", condition_held=False),
    ])
    result = evaluator.evaluate(c, evidence)
    assert result.verdict == ConstraintVerdict.UNKNOWN


def test_fail_counterexample_has_fix_context(evaluator):
    """A FAIL on a named code site must carry a non-empty fix_context."""
    evidence = make_evidence("C-CONSENT", [
        Fact(action_name="external_personal_data_export", action_occurred=True,
             filename="export.py", lineno=14, code_identifier="crm.send"),
        Fact(condition_name="explicit_consent", condition_held=False,
             filename="export.py", lineno=14, code_identifier="crm.send"),
    ])
    result = evaluator.evaluate(CONSENT_CONSTRAINT, evidence)
    assert result.verdict == ConstraintVerdict.FAIL
    assert result.counterexample is not None
    assert result.counterexample.filename == "export.py"
    assert result.counterexample.lineno == 14
    assert "export.py" in result.counterexample.fix_context
    assert result.counterexample.fix_context != ""
