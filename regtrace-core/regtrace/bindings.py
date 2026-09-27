"""
regtrace.bindings
~~~~~~~~~~~~~~~~~
Build a compact code inventory from CodeFacts and convert LLM binding
proposals into validated PolicyBindings.

Safety guarantee: an LLM-proposed alias is only accepted if it exists
in the actual CodeFactSet. Invented identifiers are never accepted.
"""
from __future__ import annotations

from regtrace.codefacts import CodeFactKind, CodeFactSet
from regtrace.matcher import PolicyBindings, TechnicalBinding


def build_code_inventory(fact_sets: list[CodeFactSet]) -> dict[str, list[str]]:
    """
    Produce a compact inventory dict for LLM consumption:

        {
          "calls":        ["crm.send", "logger.info", ...],
          "conditions":   ["customer.export_consent", ...],
          "field_accesses": ["customer.email", ...],
        }

    Deduplicates across all provided fact sets.
    """
    calls: set[str] = set()
    conditions: set[str] = set()
    fields: set[str] = set()

    for fs in fact_sets:
        for fact in fs.facts:
            if fact.kind == CodeFactKind.CALL:
                calls.add(fact.name)
            elif fact.kind == CodeFactKind.CONDITION:
                conditions.add(fact.name)
            elif fact.kind == CodeFactKind.FIELD_ACCESS:
                fields.add(fact.name)

    return {
        "calls": sorted(calls),
        "conditions": sorted(conditions),
        "field_accesses": sorted(fields),
    }


def build_bindings_from_proposals(
    proposals: dict[str, list[str]],
    fact_sets: list[CodeFactSet],
) -> PolicyBindings:
    """
    Convert LLM binding proposals into PolicyBindings.

    Aliases are validated against actual fact sets — only identifiers that
    appear in at least one CodeFactSet are accepted.

    Concepts with no valid aliases produce a TechnicalBinding with an empty
    alias list, which the matcher will map to UNKNOWN.
    """
    # Build the set of all known identifiers across all files
    known: set[str] = set()
    for fs in fact_sets:
        for fact in fs.facts:
            known.add(fact.name)
        for rel in fs.relations:
            known.add(rel.subject)
            known.add(rel.object_)

    bindings: list[TechnicalBinding] = []
    for concept, aliases in proposals.items():
        safe = [a for a in aliases if a in known]
        bindings.append(TechnicalBinding(concept=concept, aliases=safe))

    return PolicyBindings(bindings=bindings)
