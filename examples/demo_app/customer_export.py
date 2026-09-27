from __future__ import annotations

from dataclasses import dataclass


class ConsentRequiredError(Exception):
    """Raised when an external export is attempted without explicit consent."""


@dataclass
class Customer:
    email: str
    export_consent: bool


class AuditLog:
    def __init__(self) -> None:
        self.events: list[str] = []

    def log(
        self,
        event: str,
    ) -> None:
        self.events.append(
            event
        )


class CRMClient:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(
        self,
        email: str,
    ) -> None:
        self.sent.append(
            email
        )


audit = AuditLog()
crm = CRMClient()


def export_customer(
    customer: Customer,
) -> None:
    if not customer.export_consent:
        audit.log(
            "consent-missing-export-blocked"
        )
        raise ConsentRequiredError(
            "Customer has not given explicit consent for external export."
        )

    audit.log(
        "consent-observed"
    )

    crm.send(
        customer.email
    )


class CRMExportService:
    """Batch export wrapper. Enforces per-customer consent; a customer
    without consent is skipped and recorded, never sent, and does not
    block export of the remaining consenting customers."""

    def __init__(self) -> None:
        self.exported: list[str] = []
        self.blocked: list[str] = []

    def export_many(
        self,
        customers: list[Customer],
    ) -> None:
        for customer in customers:
            try:
                export_customer(customer)
            except ConsentRequiredError:
                self.blocked.append(
                    customer.email
                )
                continue

            self.exported.append(
                customer.email
            )
