"""A phone without prefix is read in the business's country (CUSTOMER-F10, CUSTOMER-F11): the country erplora.com
registered for this hub, as ``base.business.get`` answers it (the one its currency comes from), never Spain fixed in
the app. Spain only when the business says no country (a demo). Saving, editing, importing, looking up by number and
naming a card by its phone all read it the same way, and each hub reads its own."""

import pytest
from live.context import Scope
from live.operations import get

from apps.customer.models import Customer
from apps.customer.queries import business_country
from base.models import Hub

from .conftest import B, ctx_for, run

pytestmark = pytest.mark.django_db

#: A Polish mobile written as a Pole types it: no prefix, in groups of three.
POLISH = "512 345 678"


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def payload(name: str, data: dict):
    return get(name).input.model_validate(data)


def create(phone: str, **kwargs) -> Customer:
    made = run("customer.customer.create", payload("customer.customer.create", {"name": "Ana", "phone": phone}), **kwargs)
    return Customer.objects.get(pk=made.id)


def test_a_phone_without_prefix_is_read_in_the_business_s_country():
    business_in("PL")
    assert create(POLISH).phone == "+48512345678"


@pytest.mark.parametrize("country", ["ES", ""])
def test_a_business_in_spain_and_one_with_no_country_read_it_in_spain(country):
    business_in(country)
    assert create("600 111 222").phone == "+34600111222"


def test_a_phone_with_its_prefix_keeps_its_own_country_whatever_the_business_s():
    business_in("PL")
    assert create("+34 600 111 222").phone == "+34600111222"


def test_each_hub_reads_it_in_its_own_country():
    business_in("ES", "a")
    business_in("PL", "b")
    assert create(POLISH).phone == "+34512345678"
    assert create(POLISH, scope=B).phone == "+48512345678"


def test_editing_the_card_reads_it_in_the_business_s_country():
    business_in("PL")
    card = create("")
    run("customer.customer.update", payload("customer.customer.update", {"id": str(card.id), "phone": POLISH}))
    card.refresh_from_db()
    assert card.phone == "+48512345678"


def test_importing_reads_each_phone_in_the_business_s_country():
    business_in("PL")
    result = run("customer.customer.import", payload("customer.customer.import", {"rows": [{"name": "Ana", "phone": POLISH}]}))
    assert result.created == 1
    assert Customer.objects.get(name="Ana").phone == "+48512345678"


def test_the_search_by_number_reads_it_in_the_business_s_country():
    Customer.objects.create(name="Ana", phone="+48512345678")
    by_phone = payload("customer.customer.by_phone", {"phone": POLISH})
    business_in("ES")
    assert run("customer.customer.by_phone", by_phone).rows == []
    business_in("PL")
    assert [row.name for row in run("customer.customer.by_phone", by_phone).rows] == ["Ana"]


def test_a_card_named_by_its_phone_is_found_in_the_business_s_country():
    business_in("PL")
    card = Customer.objects.create(name="Ana", phone="+48512345678")
    note = run("customer.note.add", payload("customer.note.add", {"customer": POLISH, "content": "Prefers mornings"}))
    assert str(note.customer_id) == str(card.id)


def test_with_no_business_to_ask_or_no_country_it_is_spain():
    assert business_country(None) == "ES"
    business_in("")
    assert business_country(ctx_for()) == "ES"
    assert business_country(ctx_for(scope=Scope("host", "nobody"))) == "ES"
