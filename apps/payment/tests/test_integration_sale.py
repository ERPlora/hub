"""Payments and the real Sales app side by side, without doubles (WORKBOOK «Decisión: Pagos no es Ventas»).

The till's tenders (``sale.PaymentMethod``: Cash and Card from the factory, Bizum…) are how a customer
pays; a payment method here is where the business pays a supplier from. The two catalogues never mix:
neither app lists the other's, the same name lives in both, a tender is not an account to pay from,
and paying a supplier leaves the till's money untouched.

The till's factory tenders come from Sales' own migration; a transactional test flushes them, and a
reused test database keeps the flush, so every test here plants them again with that migration's own
``plant`` (idempotent), as Sales' and Invoicing's tests do.
"""

from importlib import import_module

import pytest
from django.apps import apps as registry
from django.db import connection
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import get

from apps.sale.models import PaymentMethod as Tender
from apps.sale.models import SalePayment

from .conftest import ctx_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def factory_tenders(db):
    """Cash and Card from the factory, as Sales' migration plants them (a flush took them)."""
    with connection.schema_editor() as editor:
        import_module("apps.sale.migrations.0002_factory_payment_methods").plant(registry, editor)


def run(name, data: dict | None = None):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data or {}))


def tender_names() -> set[str]:
    return {row.name for row in run("sale.payment_method.list").rows}


def test_the_tills_factory_tenders_are_not_methods_to_pay_from():
    assert {"Cash", "Card"} <= tender_names()
    assert run("payment.method.list").total == 0


def test_a_method_to_pay_from_never_shows_in_the_till():
    before = tender_names()
    run("payment.method.create", {"name": "BBVA account"})
    # The same name as the till's factory tender: two catalogues, no clash.
    run("payment.method.create", {"name": "Cash", "method_type": "cash"})
    assert tender_names() == before
    assert Tender.objects.filter(name="BBVA account").count() == 0
    assert {row.name for row in run("payment.method.list").rows} == {
        "BBVA account",
        "Cash",
    }


def test_a_till_tender_is_not_an_account_to_pay_from():
    run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    with pytest.raises(InvalidPayload) as caught:
        run(
            "payment.payment.create",
            {
                "method": "Bizum",
                "payment_date": "2026-10-10",
                "amount": 1000,
                "beneficiary_name": "Proveedor Norte SL",
            },
        )
    assert caught.value.code == "payment.method_not_found"


def test_paying_a_supplier_leaves_the_tills_money_alone():
    method = run(
        "payment.method.create", {"name": "Cash drawer", "method_type": "cash"}
    )
    payment = run(
        "payment.payment.create",
        {
            "method_id": str(method.id),
            "payment_date": "2026-10-10",
            "amount": 50_00,
            "beneficiary_name": "Frutas Paco",
        },
    )
    for step in ("approve", "mark_sent", "mark_completed"):
        run(f"payment.payment.{step}", {"id": str(payment.id)})
    assert SalePayment.objects.count() == 0
    assert not OutboxEvent.objects.filter(name__startswith="sale.").exists()
