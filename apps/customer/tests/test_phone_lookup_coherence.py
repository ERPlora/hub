"""What Customers stores, every app finds (CUSTOMER-F10, CUSTOMER-F11): a phone written without prefix is read in the
same country when Customers saves the card (inside its operation, with its context) and when another app names that
card by the same digits (``find_customer`` with no context: Appointments, Sales, Invoices, Services… call it so).
Whatever the business's country, the two never part: a card saved one way and looked up the other is a customer nobody
finds («No customer matches»). Reading it in the business's country is only right once both sides do (hub#516)."""

import pytest
from live.operations import get

from apps.customer.queries import find_customer
from base.models import Hub

from .conftest import run

pytestmark = pytest.mark.django_db

#: A Polish mobile written as a Pole types it: no prefix, in groups of three.
POLISH = "512 345 678"


@pytest.fixture(params=["PL", "ES", ""], ids=["poland", "spain", "no-country"])
def business_country(request) -> str:
    """The country erplora.com registered for the business ``a`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug="a").update(country=request.param)
    return request.param


def create(phone: str):
    data = get("customer.customer.create").input.model_validate({"name": "Ola", "phone": phone})
    return run("customer.customer.create", data).id


def test_a_card_saved_by_its_phone_is_found_by_the_same_digits_with_no_context(business_country):
    card_id = create(POLISH)
    assert find_customer(None, POLISH).id == card_id


def test_another_app_names_the_card_by_the_same_digits(business_country):
    """Services' «vouchers of a customer (by name or phone)»: the card is found (``NotFound`` otherwise) and has none."""
    create(POLISH)
    data = get("service.grant.list").input.model_validate({"customer": POLISH})
    assert run("service.grant.list", data).total == 0
