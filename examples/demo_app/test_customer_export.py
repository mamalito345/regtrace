import pytest

from demo_app.customer_export import (
    ConsentRequiredError,
    Customer,
    CRMExportService,
    crm,
    export_customer,
)


def test_customer_export_happy_path() -> None:
    crm.sent.clear()

    customer = Customer(
        email="customer@example.com",
        export_consent=True,
    )

    export_customer(customer)

    assert crm.sent == [
        "customer@example.com"
    ]


def test_customer_export_blocks_without_consent() -> None:
    crm.sent.clear()

    customer = Customer(
        email="no-consent@example.com",
        export_consent=False,
    )

    with pytest.raises(ConsentRequiredError):
        export_customer(customer)

    assert crm.sent == []


def test_crm_export_service_skips_non_consenting_customers() -> None:
    crm.sent.clear()

    service = CRMExportService()
    customers = [
        Customer(email="yes@example.com", export_consent=True),
        Customer(email="no@example.com", export_consent=False),
    ]

    service.export_many(customers)

    assert crm.sent == ["yes@example.com"]
    assert service.exported == ["yes@example.com"]
    assert service.blocked == ["no@example.com"]
