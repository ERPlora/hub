"""Payments in the business's currency (PAYMENT-F02, the old payments#35 and #38): a payment that does not say its
currency is recorded in the business's, its country's as ``base.business.get`` reads it from this hub's registry
(BASE-F50), never in a euro fixed in the app: by the screen, by the API and by the assistant (the same operation).
A payment keeps the currency it was recorded in (a record is never rewritten), and says the decimals the server counts
it in (CLDR: 2 in the forint, 0 in the yen, 3 in the Kuwaiti dinar), so the screen never asks the browser's Intl,
which gives the forint none. Each hub its own."""

import json

import pytest
from django.utils import timezone
from live.context import OperationContext
from live.operations import get

from apps.payment.models import Payment
from base.models import Hub

from .conftest import A, B, ctx_for, make_method, make_payment

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def record(method, ctx: OperationContext | None = None, **fields):
    data = {
        "method_id": str(method.id),
        "payment_date": "2026-10-10",
        "amount": 12_50,
        "beneficiary_name": "Dostawca Północ",
        **fields,
    }
    return run("payment.payment.create", data, ctx)


@pytest.fixture(autouse=True)
def business_today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: timezone.datetime(2026, 10, 28).date())


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


# A new payment


@pytest.mark.parametrize("said", [{}, {"currency": None}, {"currency": "  "}])
def test_a_payment_that_does_not_say_its_currency_is_recorded_in_the_business_s(said):
    # The old payments#35 (the screen sends none) and #38 (the assistant or the API may leave it out).
    business_in("PL")
    created = record(make_method(), **said)
    assert created.currency == "PLN"
    assert Payment.objects.get(pk=created.id).currency == "PLN"


def test_a_payment_said_in_another_currency_keeps_it():
    business_in("PL")
    assert record(make_method(), currency="eur").currency == "EUR"


def test_a_spanish_business_still_records_in_euros():
    business_in("ES")
    assert record(make_method()).currency == "EUR"


def test_an_api_key_with_only_the_permission_to_record_gets_the_business_s_currency():
    # The assistant and an integration call the same operation with the caller's own permissions: reading the
    # business is the platform's, not a permission the caller has to hold.
    business_in("PL")
    key = OperationContext(scope=A, actor="key", permissions=frozenset({"payment.add_payment"}))
    assert record(make_method(), key).currency == "PLN"


def test_the_route_records_in_the_business_s_currency(admin_client):
    business_in("PL")
    method = make_method()
    response = admin_client.post(
        "/api/payment/payments",
        json.dumps({"method_id": str(method.id), "payment_date": "2026-10-10", "amount": 1250, "beneficiary_name": "Ana"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
    )
    assert response.status_code == 201
    assert response.json()["currency"] == "PLN"


def test_each_hub_records_in_its_own_business_s_currency():
    business_in("PL", "a")
    business_in("ES", "b")
    method = make_method()
    assert record(method).currency == "PLN"
    assert record(method, ctx_for(scope=B)).currency == "EUR"


def test_the_same_attempt_sent_again_answers_the_payment_already_recorded_in_the_business_s_currency():
    # payments#8 on top of #38: the retry does not say the currency either; it is the same attempt, not a 409.
    business_in("PL")
    method = make_method()
    key = "0199f4a2-0000-7000-8000-000000000001"
    first = record(method, idempotency_key=key)
    again = record(method, idempotency_key=key)
    assert (again.id, again.currency) == (first.id, "PLN")
    assert Payment.objects.count() == 1


# A recorded payment


def test_a_recorded_payment_keeps_its_currency_when_the_business_moves():
    business_in("ES")
    created = record(make_method())
    business_in("PL")
    assert run("payment.payment.get", {"id": str(created.id)}).currency == "EUR"


@pytest.mark.parametrize(
    ("currency", "decimals"),
    [("EUR", 2), ("PLN", 2), ("HUF", 2), ("JPY", 0), ("KWD", 3)],
)
def test_a_payment_says_the_decimals_the_server_counts_its_currency_in(currency, decimals):
    payment = make_payment(currency=currency)
    listed = run("payment.payment.list", {}).rows
    assert [(row.currency, row.currency_decimals) for row in listed] == [(currency, decimals)]
    assert run("payment.payment.get", {"id": str(payment.id)}).currency_decimals == decimals


def test_the_model_has_no_euro_by_default():
    # As Sale.currency and Invoice.currency: who records a payment says its currency (the business's).
    assert not Payment._meta.get_field("currency").has_default()
