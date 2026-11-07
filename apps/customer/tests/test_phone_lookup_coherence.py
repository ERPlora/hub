"""What Customers stores, every app finds (CUSTOMER-F10, CUSTOMER-F11): a phone written without prefix is read in the
business's country (``base.operations.business_country``: the one erplora.com registered, Spain without one) when
Customers saves the card and when another app names that card by the same digits (``find_customer`` with the caller's
context: Appointments, Sales, Invoices, Services… pass theirs). Whatever the business's country, the two never part: a
card saved one way and looked up the other is a customer nobody finds («No customer matches»), hub#527. Each business
reads its own country, never another's."""

import pytest
from live.operations import get

from apps.customer.queries import find_customer
from base.models import Hub

from .conftest import B, ctx_for, run

pytestmark = pytest.mark.django_db

#: A Polish mobile written as a Pole types it: no prefix, in groups of three.
POLISH = "512 345 678"
#: How each country saves it: in Poland, a Polish mobile; in Spain (and with no country), the same digits are Spanish.
SAVED = {"PL": "+48512345678", "ES": "+34512345678", "": "+34512345678"}


@pytest.fixture(params=["PL", "ES", ""], ids=["poland", "spain", "no-country"])
def business_country(request) -> str:
    """The country erplora.com registered for the business ``a`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug="a").update(country=request.param)
    return request.param


def create(phone: str, scope=None):
    data = get("customer.customer.create").input.model_validate({"name": "Ola", "phone": phone})
    return run("customer.customer.create", data, scope=scope) if scope else run("customer.customer.create", data)


def test_a_phone_without_prefix_is_saved_in_the_business_s_country(business_country):
    assert create(POLISH).phone == SAVED[business_country]


def test_a_card_saved_by_its_phone_is_found_by_the_same_digits(business_country):
    card_id = create(POLISH).id
    assert find_customer(ctx_for(), None, POLISH).id == card_id


@pytest.mark.parametrize(
    "operation",
    [
        "service.grant.list",  # Services' «vouchers of a customer (by name or phone)»
        "appointment.appointment.list_for_customer",  # Appointments' «a customer's appointments»
    ],
)
def test_another_app_names_the_card_by_the_same_digits(business_country, operation):
    """The card is found (``NotFound`` otherwise) and has nothing yet."""
    create(POLISH)
    data = get(operation).input.model_validate({"customer": POLISH})
    assert run(operation, data).total == 0


def test_each_business_reads_the_digits_in_its_own_country():
    """``a`` in Poland and ``b`` in Spain save the same digits as two numbers, and each finds its own card by them."""
    Hub.objects.filter(slug="a").update(country="PL")
    Hub.objects.update_or_create(slug="b", defaults={"status": "ready", "country": "ES"})
    in_a, in_b = create(POLISH), create(POLISH, scope=B)
    assert (in_a.phone, in_b.phone) == ("+48512345678", "+34512345678")
    assert find_customer(ctx_for(), None, POLISH).id == in_a.id
    assert find_customer(ctx_for(scope=B), None, POLISH).id == in_b.id
