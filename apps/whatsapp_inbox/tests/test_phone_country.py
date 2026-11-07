"""The inbox reads a number written without prefix in the business's country, as Customers saves a card's phone
(hub#527, CUSTOMER-F10, CUSTOMER-F11): in a business of Poland, «512 345 678» is the conversation of +48 512 345 678
and the card Customers saved by those digits, never a Spanish number."""

import pytest

from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.queries import e164
from base.models import Hub

from .conftest import B, ctx_for, run

pytestmark = pytest.mark.django_db

#: A Polish mobile written as a Pole types it: no prefix, in groups of three.
POLISH = "512 345 678"


@pytest.fixture
def in_poland():
    """The business ``a`` registered in Poland; ``b`` in Spain."""
    Hub.objects.filter(slug="a").update(country="PL")
    Hub.objects.update_or_create(slug="b", defaults={"status": "ready", "country": "ES"})


def test_a_typed_number_without_prefix_is_one_of_the_business_s_country_never_another_business_s(in_poland):
    assert e164(POLISH, ctx_for()) == "+48512345678"
    assert e164(POLISH, ctx_for(scope=B)) == "+34512345678"


def test_a_conversation_is_named_by_its_digits_without_prefix(in_poland):
    conversation = Conversation.objects.create(phone="+48512345678", contact_name="Ola")
    detail = run("whatsapp_inbox.conversation.detail", {"conversation": POLISH})
    assert detail.id == conversation.id


def test_the_card_customers_saved_is_linked_by_the_same_digits(in_poland):
    card = run("customer.customer.create", {"name": "Ola Nowak", "phone": POLISH})
    conversation = Conversation.objects.create(phone="+48512345678", contact_name="Ola")
    linked = run(
        "whatsapp_inbox.conversation.link_customer", {"id": str(conversation.id), "customer": POLISH}
    )
    assert (card.phone, linked.customer_id) == ("+48512345678", card.id)
