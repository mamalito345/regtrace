"""
regtrace.evaluator
~~~~~~~~~~~~~~~~~~
PolicyEvaluator interface and PythonPolicyEvaluator implementation.

Evaluation logic for REQUIRE(condition) BEFORE(action) constraints.

Per-call-site model
-------------------
The matcher emits paired Facts: for each action call site, exactly one
action Fact + one condition Fact are produced consecutively.

    [action(site1), condition(site1), action(site2), condition(site2), ...]

PASS:   EVERY action fact is paired with condition_held=True.
FAIL:   ANY action fact is paired with condition_held=False.
UNKNOWN: action absent, or condition evidence missing for a site.

Severity
--------
REQUIRED (default): FAIL if violated.
RECOMMENDED: returns UNKNOWN — enforcement not yet supported in MVP.

The evaluator is domain-agnostic. It operates on Fact objects only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from regtrace.models.constraint import Constraint, ConstraintSeverity
from regtrace.models.evidence import Evidence, Fact, Counterexample
from regtrace.models.verification import ConstraintVerdict, ConstraintResult


class PolicyEvaluator(ABC):
    @abstractmethod
    def evaluate(
        self,
        constraint: Constraint,
        evidence: Evidence,
        policy_id: str = "",
        policy_title: str = "",
    ) -> ConstraintResult:
        """
        Evaluate a single constraint against the provided evidence.
        Must be deterministic — no LLM calls allowed here.
        """


class PythonPolicyEvaluator(PolicyEvaluator):
    """
    Deterministic evaluator for REQUIRE(condition) BEFORE(action) constraints.

    Reads paired (action, condition) Facts emitted by PolicyCodeMatcher.
    Each action Fact is paired with the immediately following condition Fact.
    """

    def evaluate(
        self,
        constraint: Constraint,
        evidence: Evidence,
        policy_id: str = "",
        policy_title: str = "",
    ) -> ConstraintResult:
        # RECOMMENDED constraints are not fully supported in MVP.
        if constraint.severity == ConstraintSeverity.RECOMMENDED:
            return ConstraintResult(
                constraint_id=constraint.id,
                policy_id=policy_id,
                policy_title=policy_title,
                verdict=ConstraintVerdict.UNKNOWN,
            )

        action_facts = [f for f in evidence.facts if f.is_action_fact()
                        and f.action_name == constraint.action.name]
        condition_facts = [f for f in evidence.facts if f.is_condition_fact()
                           and f.condition_name == constraint.condition.name]

        if not action_facts:
            return ConstraintResult(
                constraint_id=constraint.id,
                policy_id=policy_id,
                policy_title=policy_title,
                verdict=ConstraintVerdict.UNKNOWN,
            )

        if not condition_facts:
            return ConstraintResult(
                constraint_id=constraint.id,
                policy_id=policy_id,
                policy_title=policy_title,
                verdict=ConstraintVerdict.UNKNOWN,
            )

        # Pair up: action facts and condition facts are interleaved in order by matcher.
        # Walk them as pairs.
        verdict, cx = self._score_pairs(
            constraint, action_facts, condition_facts, evidence, policy_id, policy_title
        )
        return ConstraintResult(
            constraint_id=constraint.id,
            policy_id=policy_id,
            policy_title=policy_title,
            verdict=verdict,
            counterexample=cx,
        )

    # ------------------------------------------------------------------

    def _score_pairs(
        self,
        constraint: Constraint,
        action_facts: list[Fact],
        condition_facts: list[Fact],
        evidence: Evidence,
        policy_id: str,
        policy_title: str,
    ) -> tuple[ConstraintVerdict, Counterexample | None]:
        """
        Pair each action fact with its corresponding condition fact by index.
        If counts don't match (shouldn't happen with a correct matcher), be conservative.

        FAIL if ANY pair has condition_held=False.
        UNKNOWN if ANY pair has no corresponding condition fact.
        PASS if ALL pairs have condition_held=True.
        """
        cname = constraint.condition.name
        aname = constraint.action.name

        n_pairs = min(len(action_facts), len(condition_facts))
        if len(action_facts) != len(condition_facts):
            # Mismatch — not enough condition evidence; conservative UNKNOWN.
            return ConstraintVerdict.UNKNOWN, None

        for i in range(n_pairs):
            af = action_facts[i]
            cf = condition_facts[i]

            if cf.condition_held is False:
                cx = self._build_counterexample(
                    constraint, af, cf, evidence, policy_id, policy_title
                )
                return ConstraintVerdict.FAIL, cx

        return ConstraintVerdict.PASS, None

    def _build_counterexample(
        self,
        constraint: Constraint,
        action_fact: Fact,
        condition_fact: Fact,
        evidence: Evidence,
        policy_id: str,
        policy_title: str,
    ) -> Counterexample:
        cname = constraint.condition.name
        aname = constraint.action.name
        filename = action_fact.filename
        lineno = action_fact.lineno
        code_id = action_fact.code_identifier or aname

        loc = f"{filename}:{lineno}" if filename and lineno else (filename or "<unknown>")
        fix_context = (
            f"Ensure `{cname}` is established before the action mapped to "
            f"`{aname}` (`{code_id}` at {loc})."
        )

        return Counterexample(
            constraint_id=constraint.id,
            policy_id=policy_id,
            policy_title=policy_title,
            condition_name=cname,
            action_name=aname,
            observed=f"`{code_id}` called without `{cname}` guard at {loc}",
            expected=f"`{cname}` must be true before `{code_id}` is called",
            filename=filename,
            lineno=lineno,
            code_identifier=code_id,
            condition_alias=condition_fact.code_identifier,
            fix_context=fix_context,
            evidence=evidence,
        )
