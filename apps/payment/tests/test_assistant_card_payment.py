"""The card of recording a payment from the assistant (PAYMENT-F02): its one line says who is paid, the supplier's
invoice it pays and how much («Crear en Pagos: Pescados QA · F-2611 · 180,00 €»), the beneficiary first as the payments
list says a payment; the method it leaves from and its day follow, and nothing is said twice (hub#2292)."""

import dataclasses

import pytest
from live.operations import get

from apps.payment.tests.conftest import HUB_DB, ctx_for, make_method
from base import assistant

pytestmark = HUB_DB

CREATE = "payment.payment.create"
METHOD = "BBVA QA proveedores"
LABELS = {
    "en": {"beneficiary_name": "Beneficiary", "supplier_invoice_ref": "Supplier invoice", "amount": "Amount"},
    "es": {"beneficiary_name": "Beneficiario", "supplier_invoice_ref": "Factura del proveedor", "amount": "Importe"},
}


@pytest.fixture
def bbva():
    return make_method(METHOD, "transfer")


def sent(bbva, **more) -> dict:
    """The call of the issue: 180 euros to Pescados QA from the BBVA, today."""
    return {
        "method_id": str(bbva.id),
        "payment_date": "2026-11-23",
        "amount": 18000,
        "beneficiary_name": "Pescados QA",
        **more,
    }


def drawn(arguments: dict, language: str) -> list[dict]:
    ctx = dataclasses.replace(ctx_for(), language=language)
    return assistant.cards.card(get(CREATE), arguments, language, ctx)["fields"]


def line(arguments: dict, language: str) -> list[tuple]:
    """The card's line as the chat writes a normal write (``cardLine`` of @erplora/ui): its first three data, the
    empty ones left out."""
    shown = [field for field in drawn(arguments, language) if field["kind"] != "empty"]
    return [(field["name"], field["value"]) for field in shown[:3]]


@pytest.mark.parametrize("language", ["es", "en"])
def test_its_line_says_who_is_paid_the_invoice_and_how_much(bbva, language):
    """The issue's card said «BBVA QA proveedores · 23 nov 2026 · 180,00 €»: the method, the day and the amount."""
    arguments = sent(bbva, supplier_invoice_ref="F-2611")
    assert line(arguments, language) == [
        ("beneficiary_name", "Pescados QA"),
        ("supplier_invoice_ref", "F-2611"),
        ("amount", 18000),
    ]
    labels = {field["name"]: field["label"] for field in drawn(arguments, language)}
    assert {name: labels[name] for name in LABELS[language]} == LABELS[language]


@pytest.mark.parametrize("language", ["es", "en"])
def test_without_an_invoice_its_line_says_the_method_after_the_amount(bbva, language):
    assert line(sent(bbva), language) == [("beneficiary_name", "Pescados QA"), ("amount", 18000), ("method_id", METHOD)]


def test_the_rest_follows_as_the_form_asks_it_and_nothing_is_said_twice(bbva):
    arguments = sent(bbva, supplier_invoice_ref="F-2611", concept="Pescado de la semana", beneficiary_iban="")
    assert [field["name"] for field in drawn(arguments, "es")] == [
        "beneficiary_name",
        "supplier_invoice_ref",
        "amount",
        "method_id",
        "payment_date",
        "beneficiary_iban",
        "concept",
    ]
