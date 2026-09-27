"""
regtrace.matcher
~~~~~~~~~~~~~~~~
Generic Policy ↔ Code semantic matching.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from regtrace.codefacts import CodeFactKind, CodeFactSet, RelationKind
from regtrace.models.constraint import Constraint
from regtrace.models.evidence import Evidence, Fact


class TechnicalBinding(BaseModel):
    concept: str
    aliases: list[str]


class PolicyBindings(BaseModel):
    bindings: list[TechnicalBinding]

    def aliases_for(self, concept: str) -> list[str]:
        for binding in self.bindings:
            if binding.concept == concept:
                return binding.aliases

        return []


@dataclass
class _CallSite:
    code_identifier: str
    filename: str
    lineno: int | None


class PolicyCodeMatcher:
    """Match one policy constraint against one CodeFactSet."""

    def match(
        self,
        constraint: Constraint,
        code: CodeFactSet,
        bindings: PolicyBindings,
    ) -> Evidence:
        action_aliases = bindings.aliases_for(
            constraint.action.name
        )

        condition_aliases = bindings.aliases_for(
            constraint.condition.name
        )

        call_sites = self._find_call_sites(
            code,
            action_aliases,
        )

        if not call_sites:
            return Evidence(
                constraint_id=constraint.id,
                facts=[],
            )

        facts: list[Fact] = []

        for site in call_sites:
            facts.append(
                Fact(
                    action_name=constraint.action.name,
                    action_occurred=True,
                    filename=site.filename,
                    lineno=site.lineno,
                    code_identifier=site.code_identifier,
                )
            )

            guarded, matched_alias = self._condition_guards_call(
                code,
                condition_aliases,
                site.code_identifier,
                site.lineno,
            )

            facts.append(
                Fact(
                    condition_name=constraint.condition.name,
                    condition_held=guarded,
                    filename=site.filename if not guarded else None,
                    lineno=site.lineno if not guarded else None,
                    code_identifier=matched_alias,
                )
            )

        return Evidence(
            constraint_id=constraint.id,
            facts=facts,
        )

    def _find_call_sites(
        self,
        code: CodeFactSet,
        aliases: list[str],
    ) -> list[_CallSite]:
        alias_set = set(aliases)

        sites: list[_CallSite] = []

        for fact in code.facts:
            if (
                fact.kind == CodeFactKind.CALL
                and fact.name in alias_set
            ):
                sites.append(
                    _CallSite(
                        code_identifier=fact.name,
                        filename=code.filename,
                        lineno=fact.lineno,
                    )
                )

        return sites

    def _condition_guards_call(
        self,
        code: CodeFactSet,
        condition_aliases: list[str],
        call_name: str,
        call_lineno: int | None = None,
    ) -> tuple[bool, str | None]:
        for relation in code.relations:
            if (
                relation.kind == RelationKind.GUARDS
                and relation.object_ == call_name
                and relation.subject in condition_aliases
            ):
                if (
                    call_lineno is not None
                    and relation.object_lineno is not None
                ):
                    if relation.object_lineno != call_lineno:
                        continue

                return True, relation.subject

        return False, None