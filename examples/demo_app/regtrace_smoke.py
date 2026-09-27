from pathlib import Path

from regtrace.api import (
    verify_repository,
)
from regtrace.matcher import (
    PolicyBindings,
    TechnicalBinding,
)
from regtrace.models.constraint import (
    Action,
    Condition,
    Constraint,
    PolicySpec,
)


repository = Path(
    __file__
).resolve().parent


policy = PolicySpec(
    policy_id="P-DEMO",
    policy_title=(
        "Consent before external "
        "customer export"
    ),
    constraints=[
        Constraint(
            id="C-DEMO-1",
            condition=Condition(
                name="explicit_consent"
            ),
            action=Action(
                name="external_export"
            ),
        )
    ],
)


bindings = PolicyBindings(
    bindings=[
        TechnicalBinding(
            concept="explicit_consent",
            aliases=[
                "customer.export_consent"
            ],
        ),
        TechnicalBinding(
            concept="external_export",
            aliases=[
                "crm.send"
            ],
        ),
    ]
)


result = verify_repository(
    repository,
    policy,
    bindings,
)


print(
    "REGTRACE VERDICT: "
    f"{result.overall.value.upper()}"
)


for item in result.results:
    print(
        "Constraint: "
        f"{item.constraint_id} "
        f"-> {item.verdict.value.upper()}"
    )

    if item.counterexample is not None:
        counterexample = (
            item.counterexample
        )

        print(
            "File: "
            f"{counterexample.filename}"
        )

        print(
            "Line: "
            f"{counterexample.lineno}"
        )

        print(
            "Observed: "
            f"{counterexample.observed}"
        )

        print(
            "Expected: "
            f"{counterexample.expected}"
        )

        print(
            "Fix: "
            f"{counterexample.fix_context}"
        )