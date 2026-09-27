"""
regtrace.models.verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verdict types and the VerificationResult container.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

from regtrace.models.evidence import Counterexample


class ConstraintVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class ConstraintResult(BaseModel):
    """Result of evaluating a single Constraint against Evidence."""
    constraint_id: str
    policy_id: str = ""
    policy_title: str = ""
    verdict: ConstraintVerdict
    counterexample: Counterexample | None = None


class VerificationResult(BaseModel):
    """Unified output of a verify() call."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall: ConstraintVerdict
    overall_reason: str = ""
    results: list[ConstraintResult]

    @classmethod
    def from_results(cls, results: list[ConstraintResult]) -> "VerificationResult":
        if not results:
            return cls(
                overall=ConstraintVerdict.UNKNOWN,
                overall_reason="No applicable constraints were evaluated.",
                results=[],
            )
        if any(r.verdict == ConstraintVerdict.FAIL for r in results):
            overall = ConstraintVerdict.FAIL
            reason = ""
        elif any(r.verdict == ConstraintVerdict.UNKNOWN for r in results):
            overall = ConstraintVerdict.UNKNOWN
            reason = ""
        else:
            overall = ConstraintVerdict.PASS
            reason = ""
        return cls(overall=overall, overall_reason=reason, results=results)
