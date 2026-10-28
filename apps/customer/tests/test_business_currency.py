"""Money in the business's currency (flow customer-business-currency): its country's, as ``base.business.get`` reads it
from this hub's registry (APP-BASE-6), never a euro fixed in the app. «Spent» of the CSV export is written with the
decimals of that currency (the yen has none, the Kuwaiti dinar three); a purchase keeps the currency it was paid in
(a record is never rewritten) and says the decimals the server counts it in, so the screen never asks the browser's
Intl (which gives the forint none). Each hub its own."""

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest

from apps.customer.models import Activity, Customer, Purchase
from apps.customer.schemas import ActivityListIn, CustomerExportIn, PurchaseListIn
from base.models import Hub

from .conftest import run

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def spent_exported() -> str:
    """«total_spent» of the one card of the export."""
    result = run("customer.customer.export", CustomerExportIn())
    [row] = list(csv.DictReader(io.StringIO(result.csv)))
    return row["total_spent"]


@pytest.mark.parametrize(
    ("country", "spent", "written"),
    [
        ("ES", 1250, "12.50"),
        ("PL", 1250, "12.50"),
        ("JP", 1250, "1250"),
        ("KW", 12500, "12.500"),
    ],
)
def test_the_export_writes_spent_with_the_decimals_of_the_business_s_currency(country, spent, written):
    business_in(country)
    Customer.objects.create(name="Ana", total_spent=spent)
    assert spent_exported() == written


def test_another_hub_s_currency_does_not_change_this_one_s_export():
    business_in("ES", "a")
    business_in("JP", "b")
    Customer.objects.create(name="Ana", total_spent=1250)
    assert spent_exported() == "12.50"


def test_a_purchase_says_the_decimals_of_its_own_currency():
    business_in("PL")
    ana = Customer.objects.create(name="Ana")
    for amount, currency in [(1250, "EUR"), (1250, "JPY"), (1250, "PLN"), (1250, "")]:
        Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=amount, currency=currency, recorded_at=NOW)
    rows = run("customer.purchase.list", PurchaseListIn(customer_id=ana.id)).rows
    assert sorted((row.currency, row.currency_decimals) for row in rows) == [
        ("", None),
        ("EUR", 2),
        ("JPY", 0),
        ("PLN", 2),
    ]


def test_an_activity_entry_with_an_amount_says_the_decimals_of_its_currency():
    ana = Customer.objects.create(name="Ana")
    entries = {
        "yen": {"amount": 1250, "currency": "JPY"},
        "euro": {"amount": 1250, "currency": "EUR"},
        "none": {"amount": 1250},
        "odd": {"amount": 1250, "currency": 7},
    }
    for text, data in entries.items():
        Activity.objects.create(customer=ana, kind="purchase_recorded", text=text, data=data)
    rows = run("customer.activity.list", ActivityListIn(customer_id=ana.id)).rows
    assert {row.text: row.currency_decimals for row in rows} == {"yen": 0, "euro": 2, "none": None, "odd": None}

