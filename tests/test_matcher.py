"""
tests/test_matcher.py
~~~~~~~~~~~~~~~~~~~~~
Unit tests for PolicyCodeMatcher.

All domain vocabulary lives in test fixtures only — not in matcher logic.
Two domains are tested (privacy/export and finance/refund) to prove generality.
"""
import pytest

from regtrace.codefacts import analyze_source
from regtrace.evaluator import PythonPolicyEvaluator
from regtrace.matcher import PolicyCodeMatcher, PolicyBindings, TechnicalBinding
from regtrace.models.constraint import Constraint, Condition, Action, ConstraintSeverity
from regtrace.models.verification import ConstraintVerdict


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

matcher = PolicyCodeMatcher()
evaluator = PythonPolicyEvaluator()


def make_constraint(cid: str, condition: str, action: str) -> Constraint:
    return Constraint(
        id=cid,
        condition=Condition(name=condition),
        action=Action(name=action),
        severity=ConstraintSeverity.REQUIRED,
    )


def verdict(constraint: Constraint, source: str, bindings: PolicyBindings) -> ConstraintVerdict:
    """Full pipeline: source → CodeFacts → matcher → evaluator → verdict."""
    fs = analyze_source(source)
    evidence = matcher.match(constraint, fs, bindings)
    result = evaluator.evaluate(constraint, evidence)
    return result.verdict


# ---------------------------------------------------------------------------
# Privacy domain bindings (export consent)
# ---------------------------------------------------------------------------

EXPORT_CONSTRAINT = make_constraint(
    "C-EXPORT",
    condition="explicit_consent",
    action="external_export",
)

EXPORT_BINDINGS = PolicyBindings(bindings=[
    TechnicalBinding(concept="explicit_consent", aliases=["customer.export_consent", "customer.consent"]),
    TechnicalBinding(concept="external_export",  aliases=["crm.send", "crm.export"]),
])

UNGUARDED_EXPORT = """\
def export_customer(customer):
    crm.send(customer.email)
"""

GUARDED_EXPORT = """\
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
"""

WRONG_GUARD_EXPORT = """\
def export_customer(customer):
    if customer.is_admin:
        crm.send(customer.email)
"""

ACTION_ABSENT = """\
def get_customer(customer):
    return customer.email
"""

# ---------------------------------------------------------------------------
# 1. Unguarded action → FAIL
# ---------------------------------------------------------------------------

def test_unguarded_export_fails():
    assert verdict(EXPORT_CONSTRAINT, UNGUARDED_EXPORT, EXPORT_BINDINGS) == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 2. Correct bound guard → PASS
# ---------------------------------------------------------------------------

def test_correct_guard_passes():
    assert verdict(EXPORT_CONSTRAINT, GUARDED_EXPORT, EXPORT_BINDINGS) == ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 3. Unrelated guard → FAIL
# ---------------------------------------------------------------------------

def test_wrong_guard_fails():
    """customer.is_admin guards the call, but that is not the required condition."""
    assert verdict(EXPORT_CONSTRAINT, WRONG_GUARD_EXPORT, EXPORT_BINDINGS) == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 4. Action absent → UNKNOWN (not PASS)
# ---------------------------------------------------------------------------

def test_action_absent_is_unknown():
    assert verdict(EXPORT_CONSTRAINT, ACTION_ABSENT, EXPORT_BINDINGS) == ConstraintVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# 5. Aliases: second alias for condition also produces PASS
# ---------------------------------------------------------------------------

GUARDED_CONSENT_ALIAS = """\
def export_customer(customer):
    if customer.consent:
        crm.send(customer.email)
"""

def test_condition_alias_passes():
    """customer.consent is a registered alias for explicit_consent."""
    assert verdict(EXPORT_CONSTRAINT, GUARDED_CONSENT_ALIAS, EXPORT_BINDINGS) == ConstraintVerdict.PASS


GUARDED_CRM_EXPORT_ALIAS = """\
def export_customer(customer):
    if customer.export_consent:
        crm.export(customer.email)
"""

def test_action_alias_passes():
    """crm.export is a registered alias for external_export."""
    assert verdict(EXPORT_CONSTRAINT, GUARDED_CRM_EXPORT_ALIAS, EXPORT_BINDINGS) == ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 6. Finance domain: manager_approval / high_value_refund — same matcher
# ---------------------------------------------------------------------------

REFUND_CONSTRAINT = make_constraint(
    "C-REFUND",
    condition="manager_approval",
    action="high_value_refund",
)

REFUND_BINDINGS = PolicyBindings(bindings=[
    TechnicalBinding(concept="manager_approval", aliases=["order.manager_approved"]),
    TechnicalBinding(concept="high_value_refund", aliases=["payments.refund"]),
])

GUARDED_REFUND = """\
def refund(order, amount):
    if order.manager_approved:
        payments.refund(order.id, amount)
"""

UNGUARDED_REFUND = """\
def refund(order, amount):
    payments.refund(order.id, amount)
"""

def test_guarded_refund_passes():
    assert verdict(REFUND_CONSTRAINT, GUARDED_REFUND, REFUND_BINDINGS) == ConstraintVerdict.PASS


def test_unguarded_refund_fails():
    assert verdict(REFUND_CONSTRAINT, UNGUARDED_REFUND, REFUND_BINDINGS) == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 7. Nested guards: outer condition also satisfies the requirement
# ---------------------------------------------------------------------------

NESTED_GUARDED_EXPORT = """\
def export_customer(customer):
    if customer.export_consent:
        if customer.is_active:
            crm.send(customer.email)
"""

def test_nested_outer_guard_passes():
    """export_consent is on the outer guard stack — should still PASS."""
    assert verdict(EXPORT_CONSTRAINT, NESTED_GUARDED_EXPORT, EXPORT_BINDINGS) == ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 8. Missing/empty binding never silently passes
# ---------------------------------------------------------------------------

EMPTY_BINDINGS = PolicyBindings(bindings=[])

def test_empty_bindings_is_unknown():
    """No bindings → action never found → UNKNOWN, never PASS."""
    result = verdict(EXPORT_CONSTRAINT, UNGUARDED_EXPORT, EMPTY_BINDINGS)
    assert result == ConstraintVerdict.UNKNOWN


PARTIAL_BINDINGS = PolicyBindings(bindings=[
    TechnicalBinding(concept="external_export", aliases=["crm.send"]),
    # condition binding deliberately omitted
])

def test_missing_condition_binding_fails():
    """Action found, condition binding absent → no GUARDS match → FAIL."""
    assert verdict(EXPORT_CONSTRAINT, GUARDED_EXPORT, PARTIAL_BINDINGS) == ConstraintVerdict.FAIL
