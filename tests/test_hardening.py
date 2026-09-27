"""
tests/test_hardening.py
~~~~~~~~~~~~~~~~~~~~~~~
Adversarial regression tests for M5.1 hardening.

Covers all five categories:
  1. Multiple call-site false PASS (B1)
  2. Empty policy → UNKNOWN, not PASS (B2)
  3. Source location in FAIL counterexample (B3)
  4. Deterministic fix_context (B4)
  5. Policy/constraint identity in results (B5)
  6. RECOMMENDED severity → UNKNOWN (B6)
  7. Duplicate constraint IDs → validation error (B7)
"""
import pytest

from regtrace.api import verify
from regtrace.codefacts import analyze_source
from regtrace.evaluator import PythonPolicyEvaluator
from regtrace.matcher import PolicyCodeMatcher, PolicyBindings, TechnicalBinding
from regtrace.models.constraint import (
    Constraint, Condition, Action, ConstraintSeverity, PolicySpec,
)
from regtrace.models.evidence import Fact, Evidence
from regtrace.models.verification import ConstraintVerdict, VerificationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXPORT_POLICY = PolicySpec(
    policy_id="P-TEST",
    policy_title="Test consent policy",
    constraints=[
        Constraint(
            id="C-EXPORT",
            condition=Condition(name="explicit_consent"),
            action=Action(name="external_export"),
            severity=ConstraintSeverity.REQUIRED,
        )
    ],
)

EXPORT_BINDINGS = PolicyBindings(bindings=[
    TechnicalBinding(concept="explicit_consent", aliases=["customer.export_consent"]),
    TechnicalBinding(concept="external_export",  aliases=["crm.send"]),
])


def pipeline_verdict(source: str, policy=EXPORT_POLICY, bindings=EXPORT_BINDINGS,
                     filename: str = "test.py") -> VerificationResult:
    return verify(source, policy, bindings, filename=filename)


# ---------------------------------------------------------------------------
# 1. MULTIPLE CALL-SITE FALSE PASS
# ---------------------------------------------------------------------------

ONE_GUARDED_ONE_UNGUARDED = """\
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)

    crm.send(customer.phone)
"""

def test_one_guarded_one_unguarded_must_fail():
    """Critical regression: one guarded + one unguarded call → FAIL, not PASS."""
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED)
    assert result.overall == ConstraintVerdict.FAIL


TWO_GUARDED = """\
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
        crm.send(customer.phone)
"""

def test_two_guarded_calls_pass():
    """Both call sites guarded → PASS."""
    result = pipeline_verdict(TWO_GUARDED)
    assert result.overall == ConstraintVerdict.PASS


TWO_UNGUARDED = """\
def export_customer(customer):
    crm.send(customer.email)
    crm.send(customer.phone)
"""

def test_two_unguarded_calls_fail():
    """Two unguarded call sites → FAIL."""
    result = pipeline_verdict(TWO_UNGUARDED)
    assert result.overall == ConstraintVerdict.FAIL


NESTED_GUARDED = """\
def export_customer(customer):
    if customer.export_consent:
        if customer.is_active:
            crm.send(customer.email)
"""

def test_nested_correct_guards_pass():
    """Inner call guarded by outer correct condition → PASS."""
    result = pipeline_verdict(NESTED_GUARDED)
    assert result.overall == ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 2. EMPTY POLICY → UNKNOWN, never PASS
# ---------------------------------------------------------------------------

def test_empty_constraints_list_is_unknown():
    """PolicySpec with no constraints → overall UNKNOWN."""
    empty_policy = PolicySpec(policy_id="P-EMPTY", constraints=[])
    result = verify("def f(): pass", empty_policy, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.UNKNOWN
    assert result.overall_reason != ""
    assert len(result.results) == 0


def test_empty_constraints_never_pass():
    """Empty constraint list must NOT return PASS even for benign code."""
    empty_policy = PolicySpec(policy_id="P-EMPTY", constraints=[])
    result = verify("x = 1 + 1", empty_policy, EXPORT_BINDINGS)
    assert result.overall != ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 3. SOURCE LOCATION IN FAIL COUNTEREXAMPLE
# ---------------------------------------------------------------------------

def test_fail_counterexample_has_filename():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED, filename="mymodule/export.py")
    assert result.overall == ConstraintVerdict.FAIL
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    assert failing
    cx = failing[0].counterexample
    assert cx is not None
    assert cx.filename == "mymodule/export.py"


def test_fail_counterexample_has_lineno():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED, filename="export.py")
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    cx = failing[0].counterexample
    assert cx is not None
    assert cx.lineno is not None
    assert isinstance(cx.lineno, int)


def test_fail_counterexample_has_code_identifier():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED, filename="export.py")
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    cx = failing[0].counterexample
    assert cx is not None
    assert cx.code_identifier == "crm.send"


# ---------------------------------------------------------------------------
# 4. DETERMINISTIC FIX CONTEXT
# ---------------------------------------------------------------------------

def test_fail_has_nonempty_fix_context():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED, filename="export.py")
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    cx = failing[0].counterexample
    assert cx is not None
    assert cx.fix_context != ""
    # Must mention the required condition concept
    assert "explicit_consent" in cx.fix_context


def test_fix_context_mentions_file_and_line():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED, filename="export.py")
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    cx = failing[0].counterexample
    assert "export.py" in cx.fix_context


# ---------------------------------------------------------------------------
# 5. POLICY AND CONSTRAINT IDENTITY IN RESULTS
# ---------------------------------------------------------------------------

def test_result_carries_policy_id():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED)
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    assert failing[0].policy_id == "P-TEST"


def test_result_carries_policy_title():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED)
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    assert failing[0].policy_title == "Test consent policy"


def test_result_carries_constraint_id():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED)
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    assert failing[0].constraint_id == "C-EXPORT"


def test_counterexample_carries_policy_id():
    result = pipeline_verdict(ONE_GUARDED_ONE_UNGUARDED)
    failing = [r for r in result.results if r.verdict == ConstraintVerdict.FAIL]
    cx = failing[0].counterexample
    assert cx is not None
    assert cx.policy_id == "P-TEST"


# ---------------------------------------------------------------------------
# 6. RECOMMENDED SEVERITY → UNKNOWN
# ---------------------------------------------------------------------------

def test_recommended_constraint_returns_unknown():
    policy = PolicySpec(
        policy_id="P-REC",
        constraints=[
            Constraint(
                id="C-REC",
                condition=Condition(name="explicit_consent"),
                action=Action(name="external_export"),
                severity=ConstraintSeverity.RECOMMENDED,
            )
        ],
    )
    # Even unguarded code with RECOMMENDED constraint → UNKNOWN (not FAIL)
    result = verify(ONE_GUARDED_ONE_UNGUARDED, policy, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# 7. DUPLICATE CONSTRAINT IDS → VALIDATION ERROR
# ---------------------------------------------------------------------------

def test_duplicate_constraint_ids_raise_validation_error():
    with pytest.raises(Exception, match="duplicate constraint id"):
        PolicySpec(
            policy_id="P-DUP",
            constraints=[
                Constraint(
                    id="C-SAME",
                    condition=Condition(name="cond_a"),
                    action=Action(name="act_a"),
                ),
                Constraint(
                    id="C-SAME",   # duplicate
                    condition=Condition(name="cond_b"),
                    action=Action(name="act_b"),
                ),
            ],
        )
