from __future__ import annotations

from pathlib import Path
from typing import Collection, Iterable

from regtrace.bindings import (
    build_bindings_from_proposals,
    build_code_inventory,
)
from regtrace.codefacts import (
    CodeFactSet,
    PythonCodeFactsProvider,
)
from regtrace.evaluator import (
    PythonPolicyEvaluator,
)
from regtrace.llm import (
    BindingProposalError,
    LLMProvider,
    PolicyCompiler,
    PolicyCompilerError,
    explain,
    plan,
    propose_bindings,
)
from regtrace.matcher import (
    PolicyBindings,
    PolicyCodeMatcher,
)
from regtrace.models.constraint import (
    PolicySpec,
)
from regtrace.models.evidence import (
    Evidence,
)
from regtrace.models.verification import (
    ConstraintResult,
    ConstraintVerdict,
    VerificationResult,
)
from regtrace.repository import (
    RepositoryAnalysis,
    RepositoryAnalyzer,
)


_provider = PythonCodeFactsProvider()
_matcher = PolicyCodeMatcher()
_evaluator = PythonPolicyEvaluator()


def _verify_fact_sets(
    fact_sets: Iterable[CodeFactSet],
    policy: PolicySpec,
    bindings: PolicyBindings,
) -> VerificationResult:
    code_sets = tuple(
        fact_sets
    )

    results: list[
        ConstraintResult
    ] = []

    for constraint in policy.constraints:
        combined_facts = []

        for code in code_sets:
            evidence = _matcher.match(
                constraint,
                code,
                bindings,
            )

            combined_facts.extend(
                evidence.facts
            )

        result = _evaluator.evaluate(
            constraint,
            Evidence(
                constraint_id=constraint.id,
                facts=combined_facts,
            ),
            policy_id=policy.policy_id,
            policy_title=policy.policy_title,
        )

        results.append(
            result
        )

    return VerificationResult.from_results(
        results
    )


def _apply_repository_issues(
    result: VerificationResult,
    analysis: RepositoryAnalysis,
) -> VerificationResult:
    if not analysis.issues:
        return result

    issue_files = ", ".join(
        issue.filename
        for issue in analysis.issues[:5]
    )

    if len(analysis.issues) > 5:
        issue_files += (
            f", +{len(analysis.issues) - 5} more"
        )

    reason = (
        "Repository analysis was incomplete: "
        f"{len(analysis.issues)} file(s) "
        f"could not be analyzed "
        f"({issue_files})."
    )

    if (
        result.overall
        == ConstraintVerdict.FAIL
    ):
        return VerificationResult(
            overall=ConstraintVerdict.FAIL,
            overall_reason=(
                f"Known violation found. {reason}"
            ),
            results=result.results,
        )

    return VerificationResult(
        overall=ConstraintVerdict.UNKNOWN,
        overall_reason=reason,
        results=result.results,
    )


def verify(
    source_code: str,
    policy: PolicySpec,
    bindings: PolicyBindings,
    filename: str = "<memory>",
) -> VerificationResult:
    code = _provider.analyze_source(
        source_code,
        filename=filename,
    )

    return _verify_fact_sets(
        (code,),
        policy,
        bindings,
    )


def verify_repository(
    repository_path: str | Path,
    policy: PolicySpec,
    bindings: PolicyBindings,
    ignored_directories: Collection[str]
    | None = None,
) -> VerificationResult:
    analysis = RepositoryAnalyzer(
        ignored_directories=ignored_directories,
    ).analyze(
        repository_path
    )

    result = _verify_fact_sets(
        analysis.fact_sets,
        policy,
        bindings,
    )

    return _apply_repository_issues(
        result,
        analysis,
    )


def explain_feature(
    feature_intent: str,
    policy_text: str,
    provider: LLMProvider,
) -> str:
    return explain(
        feature_intent,
        policy_text,
        provider,
    )


def plan_feature(
    feature_intent: str,
    policy_text: str,
    provider: LLMProvider,
) -> str:
    return plan(
        feature_intent,
        policy_text,
        provider,
    )


def verify_with_text(
    repository_path: str | Path,
    policy_text: str,
    feature_intent: str,
    provider: LLMProvider,
    ignored_directories: Collection[str]
    | None = None,
    policy_id: str = "P-auto",
) -> VerificationResult:
    try:
        policy = PolicyCompiler(
            provider
        ).compile(
            policy_text,
            policy_id=policy_id,
        )

    except PolicyCompilerError as exc:
        return VerificationResult(
            overall=ConstraintVerdict.UNKNOWN,
            overall_reason=(
                "Policy could not be compiled: "
                f"{exc}"
            ),
            results=[],
        )

    analysis = RepositoryAnalyzer(
        ignored_directories=ignored_directories,
    ).analyze(
        repository_path
    )

    if not analysis.fact_sets:
        if analysis.issues:
            issue_files = ", ".join(
                issue.filename
                for issue in analysis.issues[:5]
            )

            return VerificationResult(
                overall=ConstraintVerdict.UNKNOWN,
                overall_reason=(
                    "Repository could not be verified "
                    "because no Python file was "
                    "successfully analyzed. "
                    f"Problem files: {issue_files}."
                ),
                results=[],
            )

        return VerificationResult(
            overall=ConstraintVerdict.UNKNOWN,
            overall_reason=(
                "No Python files were found "
                "in the repository."
            ),
            results=[],
        )

    inventory = build_code_inventory(
        list(
            analysis.fact_sets
        )
    )

    concepts: list[str] = []

    for constraint in policy.constraints:
        concepts.extend(
            (
                constraint.condition.name,
                constraint.action.name,
            )
        )

    concepts = list(
        dict.fromkeys(
            concepts
        )
    )

    try:
        proposals = propose_bindings(
            concepts,
            inventory,
            provider,
            feature_intent=feature_intent,
        )

    except BindingProposalError as exc:
        return VerificationResult(
            overall=ConstraintVerdict.UNKNOWN,
            overall_reason=(
                "Binding proposal failed: "
                f"{exc}"
            ),
            results=[],
        )

    bindings = build_bindings_from_proposals(
        proposals,
        list(
            analysis.fact_sets
        ),
    )

    unresolved = [
        concept
        for concept in concepts
        if not bindings.aliases_for(
            concept
        )
    ]

    if unresolved:
        return VerificationResult(
            overall=ConstraintVerdict.UNKNOWN,
            overall_reason=(
                "Required semantic bindings "
                "could not be resolved from "
                "actual code: "
                + ", ".join(unresolved)
            ),
            results=[],
        )

    result = _verify_fact_sets(
        analysis.fact_sets,
        policy,
        bindings,
    )

    return _apply_repository_issues(
        result,
        analysis,
    )