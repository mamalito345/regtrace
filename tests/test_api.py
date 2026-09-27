"""
tests/test_api.py
~~~~~~~~~~~~~~~~~
End-to-end tests for regtrace.api.verify().

All domain vocabulary (consent, CRM, refund) lives only in fixtures —
the verify() function itself is domain-agnostic.
"""
import pytest

from regtrace.api import verify
from regtrace.matcher import PolicyBindings, TechnicalBinding
from regtrace.models.constraint import (
    Constraint, Condition, Action, ConstraintSeverity, PolicySpec,
)
from regtrace.models.verification import ConstraintVerdict


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_policy(cid: str, condition: str, action: str) -> PolicySpec:
    return PolicySpec(
        policy_id="TEST",
        constraints=[
            Constraint(
                id=cid,
                condition=Condition(name=condition),
                action=Action(name=action),
                severity=ConstraintSeverity.REQUIRED,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Export / consent domain
# ---------------------------------------------------------------------------

EXPORT_POLICY = make_policy("C-EXPORT", "explicit_consent", "external_export")

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

ACTION_ABSENT = """\
def get_customer(customer):
    return customer.email
"""

WRONG_GUARD = """\
def export_customer(customer):
    if customer.is_admin:
        crm.send(customer.email)
"""


# ---------------------------------------------------------------------------
# 4. Unguarded export → FAIL end-to-end
# ---------------------------------------------------------------------------

def test_unguarded_export_is_fail():
    result = verify(UNGUARDED_EXPORT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 5. Correctly guarded export → PASS end-to-end
# ---------------------------------------------------------------------------

def test_guarded_export_is_pass():
    result = verify(GUARDED_EXPORT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.PASS


# ---------------------------------------------------------------------------
# 6. Absent action → UNKNOWN end-to-end
# ---------------------------------------------------------------------------

def test_absent_action_is_unknown():
    result = verify(ACTION_ABSENT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# 7. Finance domain: manager_approval / high_value_refund — same verify()
# ---------------------------------------------------------------------------

REFUND_POLICY = make_policy("C-REFUND", "manager_approval", "high_value_refund")

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

def test_guarded_refund_is_pass():
    result = verify(GUARDED_REFUND, REFUND_POLICY, REFUND_BINDINGS)
    assert result.overall == ConstraintVerdict.PASS


def test_unguarded_refund_is_fail():
    result = verify(UNGUARDED_REFUND, REFUND_POLICY, REFUND_BINDINGS)
    assert result.overall == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 8. Unknown/missing binding never silently passes
# ---------------------------------------------------------------------------

def test_empty_bindings_is_unknown():
    result = verify(UNGUARDED_EXPORT, EXPORT_POLICY, PolicyBindings(bindings=[]))
    assert result.overall == ConstraintVerdict.UNKNOWN


def test_wrong_guard_fails():
    """A guard that is not the required condition must still FAIL."""
    result = verify(WRONG_GUARD, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 9. Overall FAIL dominates PASS
# ---------------------------------------------------------------------------

def test_fail_dominates_pass():
    """Two constraints: one PASS, one FAIL → overall FAIL."""
    policy = PolicySpec(
        policy_id="MULTI",
        constraints=[
            Constraint(
                id="C-1",
                condition=Condition(name="explicit_consent"),
                action=Action(name="external_export"),
                severity=ConstraintSeverity.REQUIRED,
            ),
            Constraint(
                id="C-2",
                condition=Condition(name="manager_approval"),
                action=Action(name="high_value_refund"),
                severity=ConstraintSeverity.REQUIRED,
            ),
        ],
    )
    # Bindings only cover consent/export → refund constraint has no action binding → UNKNOWN
    # But export is unguarded → FAIL
    # FAIL dominates UNKNOWN
    result = verify(UNGUARDED_EXPORT, policy, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.FAIL


# ---------------------------------------------------------------------------
# 10. Overall UNKNOWN preserved when no FAIL exists
# ---------------------------------------------------------------------------

def test_unknown_preserved_when_no_fail():
    """Action absent in source, no FAIL constraint → overall UNKNOWN."""
    result = verify(ACTION_ABSENT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.overall == ConstraintVerdict.UNKNOWN
    assert all(r.verdict != ConstraintVerdict.FAIL for r in result.results)


# ---------------------------------------------------------------------------
# Structural checks on VerificationResult
# ---------------------------------------------------------------------------

def test_result_contains_per_constraint_results():
    result = verify(UNGUARDED_EXPORT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert len(result.results) == 1
    assert result.results[0].constraint_id == "C-EXPORT"


def test_result_has_id_and_timestamp():
    result = verify(GUARDED_EXPORT, EXPORT_POLICY, EXPORT_BINDINGS)
    assert result.id  # UUID string, non-empty
    assert result.timestamp is not None
