"""A customer named in words instead of by her id, as every app's operation gets her (``find_customer``, hub#2329).

What is exactly her email, her phone or her name names her first; when nothing is, the words name the cards the
Customers list finds with them (CUSTOMER-F02): a part of her name, with or without accents. Two that fit are a
refusal that names them, so the person can say which one; the words of a contact detail only work for whoever
sees the customers' contact details (BASE-F119)."""

import pytest
from django.utils import timezone, translation
from live.errors import Conflict, NotFound

from apps.customer.models import Customer
from apps.customer.schemas.fields import CustomerRefIn
from base import listing
from base.permissions import permissions_of_role
from base.sensitive import VIEW_CUSTOMER_CONTACT

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


def card(name: str, **fields) -> Customer:
    return Customer.objects.create(name=name, **fields)


def named(reference: str, ctx=None) -> Customer:
    from live.operations import get

    op = get("customer.customer.detail")
    return op(ctx or ctx_for(), CustomerRefIn(customer=reference))


def without_contact():
    return ctx_for(permissions=permissions_of_role("hub_employee") - {VIEW_CUSTOMER_CONTACT})


@pytest.mark.parametrize("reference", ["Lucía Fernández", "Fernández", "lucia", "LUCIA FERNANDEZ", " fernández qa "])
def test_a_part_of_her_name_names_her_with_or_without_accents(reference):
    lucia = card("Lucía Fernández QA")
    card("Carmen Ruiz")
    assert named(reference).id == lucia.id


def test_her_exact_name_names_her_before_the_cards_that_hold_it():
    ana = card("Ana García")
    card("Ana García López")
    assert named("ana garcia").id == ana.id


@pytest.mark.parametrize("language", ["es", "en"])
def test_two_cards_that_hold_the_words_are_named_in_the_refusal_as_a_screen_joins_them(language):
    card("Lucía Gómez")
    card("Lucía Fernández QA")
    card("Carmen Ruiz")
    with translation.override(language), pytest.raises(Conflict) as refused:
        named("Lucía", ctx_for(language=language))
    assert refused.value.code == "customer.customer_ambiguous"
    message = refused.value.message
    assert listing.joined(["Lucía Fernández QA", "Lucía Gómez"], language) in message
    assert "Carmen Ruiz" not in message


def test_the_refusal_names_five_cards_at_most():
    for surname in ("Alba", "Blanco", "Cano", "Díaz", "Egea", "Font"):
        card(f"Lucía {surname}")
    with pytest.raises(Conflict) as refused:
        named("Lucía")
    message = refused.value.message
    assert "Lucía Egea" in message
    assert "Lucía Font" not in message


def test_a_card_no_longer_live_is_not_named_by_a_part_of_its_name():
    card("Lucía Fernández QA", deleted_at=timezone.now())
    with pytest.raises(NotFound) as refused:
        named("Lucía")
    assert refused.value.code == "customer.customer_unavailable"
    gomez = card("Lucía Gómez")
    assert named("Lucía").id == gomez.id


@pytest.mark.parametrize("reference", ["600 222", "lucia.fernandez@"])
def test_a_part_of_her_contact_names_her_only_for_whoever_sees_it(reference):
    lucia = card("Lucía Fernández QA", phone="+34600222333", email="lucia.fernandez@example.com")
    assert named(reference).id == lucia.id
    with pytest.raises(NotFound) as refused:
        named(reference, without_contact())
    assert refused.value.code == "customer.customer_unavailable"
