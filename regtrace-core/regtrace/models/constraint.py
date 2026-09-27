"""
regtrace.models.constraint
~~~~~~~~~~~~~~~~~~~~~~~~~~
Generic constraint IR for REQUIRE(condition) BEFORE(action) policies.
No domain-specific logic lives here.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator


class ConstraintSeverity(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"


class Condition(BaseModel):
    """A named boolean condition that must hold before an action is permitted."""

    name: str
    description: str = ""


class Action(BaseModel):
    """A named operation that is governed by a condition."""

    name: str
    description: str = ""


class Constraint(BaseModel):
    """A single REQUIRE(condition) BEFORE(action) constraint."""

    id: str
    requirement_id: str = ""
    type: Literal["require_before"] = "require_before"
    condition: Condition
    action: Action
    severity: ConstraintSeverity = ConstraintSeverity.REQUIRED
    description: str = ""


class PolicySpec(BaseModel):
    """Structured policy representation consumed by the deterministic evaluator."""

    policy_id: str
    policy_title: str = ""
    constraints: list[Constraint]
    explanation: str = ""

    @model_validator(mode="after")
    def _check_unique_constraint_ids(self) -> "PolicySpec":
        seen: set[str] = set()

        for constraint in self.constraints:
            if constraint.id in seen:
                raise ValueError(
                    f"PolicySpec '{self.policy_id}' contains duplicate constraint id: "
                    f"'{constraint.id}'"
                )

            seen.add(constraint.id)

        return self