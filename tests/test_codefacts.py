"""
tests/test_codefacts.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for PythonCodeFactsProvider.

All tests operate on generic source snippets — no policy-domain keywords
in the assertions except the names that appear in the test source itself.
"""
import pytest

from regtrace.codefacts import (
    analyze_source,
    AnalysisError,
    CodeFactKind,
    RelationKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def facts_of(fs, kind: CodeFactKind) -> list[str]:
    return [f.name for f in fs.facts if f.kind == kind]


def has_relation(fs, kind: RelationKind, subject: str, object_: str) -> bool:
    return any(
        r.kind == kind and r.subject == subject and r.object_ == object_
        for r in fs.relations
    )


# ---------------------------------------------------------------------------
# 1. Unguarded call extraction
# ---------------------------------------------------------------------------

UNGUARDED = """\
def export_customer(customer):
    crm.send(customer.email)
"""

def test_unguarded_call_function_fact():
    fs = analyze_source(UNGUARDED)
    assert "export_customer" in facts_of(fs, CodeFactKind.FUNCTION)

def test_unguarded_call_call_fact():
    fs = analyze_source(UNGUARDED)
    assert "crm.send" in facts_of(fs, CodeFactKind.CALL)

def test_unguarded_call_no_guard_relation():
    """crm.send must NOT appear as the object of any GUARDS relation."""
    fs = analyze_source(UNGUARDED)
    guarded_targets = {r.object_ for r in fs.relations if r.kind == RelationKind.GUARDS}
    assert "crm.send" not in guarded_targets

def test_unguarded_call_function_calls_relation():
    fs = analyze_source(UNGUARDED)
    assert has_relation(fs, RelationKind.CALLS, "export_customer", "crm.send")


# ---------------------------------------------------------------------------
# 2. Guarded call extraction
# ---------------------------------------------------------------------------

GUARDED = """\
def export_customer(customer):
    if customer.export_consent:
        crm.send(customer.email)
"""

def test_guarded_call_condition_fact():
    fs = analyze_source(GUARDED)
    assert "customer.export_consent" in facts_of(fs, CodeFactKind.CONDITION)

def test_guarded_call_guards_relation():
    fs = analyze_source(GUARDED)
    assert has_relation(fs, RelationKind.GUARDS, "customer.export_consent", "crm.send")

def test_guarded_call_still_has_call_fact():
    fs = analyze_source(GUARDED)
    assert "crm.send" in facts_of(fs, CodeFactKind.CALL)


# ---------------------------------------------------------------------------
# 3. Field access extraction
# ---------------------------------------------------------------------------

def test_field_access_email():
    fs = analyze_source(UNGUARDED)
    assert "customer.email" in facts_of(fs, CodeFactKind.FIELD_ACCESS)

def test_field_access_consent():
    fs = analyze_source(GUARDED)
    assert "customer.export_consent" in facts_of(fs, CodeFactKind.FIELD_ACCESS)

def test_field_access_contains_relation():
    fs = analyze_source(UNGUARDED)
    assert has_relation(fs, RelationKind.CONTAINS, "export_customer", "customer.email")


# ---------------------------------------------------------------------------
# 4. Direct argument flow extraction
# ---------------------------------------------------------------------------

def test_flows_to_email_to_crm_send():
    """customer.email FLOWS_TO crm.send at argument position 0."""
    fs = analyze_source(UNGUARDED)
    assert has_relation(fs, RelationKind.FLOWS_TO, "customer.email", "crm.send")

def test_flows_to_detail_is_argument_index():
    fs = analyze_source(UNGUARDED)
    rel = next(
        r for r in fs.relations
        if r.kind == RelationKind.FLOWS_TO
        and r.subject == "customer.email"
        and r.object_ == "crm.send"
    )
    assert rel.detail == "0"


# ---------------------------------------------------------------------------
# 5. Unrelated domain — refund example
# ---------------------------------------------------------------------------

REFUND = """\
def refund(order, amount):
    if order.manager_approved:
        payments.refund(order.id, amount)
"""

def test_refund_function_fact():
    fs = analyze_source(REFUND)
    assert "refund" in facts_of(fs, CodeFactKind.FUNCTION)

def test_refund_condition_fact():
    fs = analyze_source(REFUND)
    assert "order.manager_approved" in facts_of(fs, CodeFactKind.CONDITION)

def test_refund_call_fact():
    fs = analyze_source(REFUND)
    assert "payments.refund" in facts_of(fs, CodeFactKind.CALL)

def test_refund_guards_relation():
    fs = analyze_source(REFUND)
    assert has_relation(fs, RelationKind.GUARDS, "order.manager_approved", "payments.refund")

def test_refund_order_id_flows_to_payment():
    fs = analyze_source(REFUND)
    assert has_relation(fs, RelationKind.FLOWS_TO, "order.id", "payments.refund")


# ---------------------------------------------------------------------------
# 6. Nested if — inner guard is preserved
# ---------------------------------------------------------------------------

NESTED = """\
def process(req):
    if req.authenticated:
        if req.has_permission:
            db.write(req.data)
"""

def test_nested_outer_condition_fact():
    fs = analyze_source(NESTED)
    assert "req.authenticated" in facts_of(fs, CodeFactKind.CONDITION)

def test_nested_inner_condition_fact():
    fs = analyze_source(NESTED)
    assert "req.has_permission" in facts_of(fs, CodeFactKind.CONDITION)

def test_nested_inner_guards_call():
    fs = analyze_source(NESTED)
    assert has_relation(fs, RelationKind.GUARDS, "req.has_permission", "db.write")

def test_nested_outer_also_guards_call():
    """The outer condition is still on the stack when db.write is visited."""
    fs = analyze_source(NESTED)
    assert has_relation(fs, RelationKind.GUARDS, "req.authenticated", "db.write")


# ---------------------------------------------------------------------------
# 7. Syntax error fails clearly
# ---------------------------------------------------------------------------

def test_syntax_error_raises_analysis_error():
    with pytest.raises(AnalysisError, match="Syntax error"):
        analyze_source("def broken(:\n    pass", filename="bad.py")

def test_syntax_error_no_facts_emitted():
    """AnalysisError must be raised; no partial fact set returned."""
    try:
        analyze_source("def broken(:\n    pass")
        assert False, "Should have raised"
    except AnalysisError:
        pass  # correct — no silent partial result
