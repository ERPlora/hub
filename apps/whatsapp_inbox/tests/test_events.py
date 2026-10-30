"""The WhatsApp inbox's events and its reactions to Customers (WHATSAPP_INBOX-F04, F11, F12).

Each reaction is driven by the very event Customers records in its outbox when its own operation runs
(create, update, merge, erase): the dependency is real, never a mock. The relay of phase 2 hands the
delivered event to ``events.react``; here the test hands it over the same way, twice where the outbox
may deliver twice.
"""

import pytest
from live.models import OutboxEvent

from apps.whatsapp_inbox import events
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import A, card, receive, run

pytestmark = pytest.mark.django_db


def delivered(name: str):
    """Hand the last ``name`` event Customers recorded to the inbox, as the relay will."""
    payload = (
        OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload
    )
    return events.react(A, name, payload)


def conversation() -> Conversation:
    return Conversation.objects.get()


def test_the_reactions_are_declared_by_name():
    assert events.REACTIONS == {
        "customer.customer.created": "whatsapp_inbox.conversation.claim_for_customer",
        "customer.customer.updated": "whatsapp_inbox.conversation.claim_for_customer",
        "customer.customer.merged": "whatsapp_inbox.conversation.move_customer",
        "customer.customer.deleted": "whatsapp_inbox.conversation.release_customer",
        "customer.customer.erased": "whatsapp_inbox.conversation.erase_for_customer",
    }
    assert events.react(A, "sale.sale.completed", {"id": "x"}) is None


def test_every_event_of_the_app_is_named_once():
    assert len(events.ALL) == len(set(events.ALL)) == 18
    assert {events.CHANNEL_CONNECTED, events.CHANNEL_DISCONNECTED} == {
        "whatsapp_inbox.channel.connected",
        "whatsapp_inbox.channel.disconnected",
    }
    assert all(name.startswith("whatsapp_inbox.") for name in events.ALL)


def test_a_card_created_with_her_number_claims_her_conversation():
    receive("wamid.1", "34600111222")
    assert conversation().customer_id is None
    ana = card("Ana López", "600 111 222")
    assert delivered("customer.customer.created").count == 1
    assert conversation().customer_id == ana.id
    # Delivered again: nothing more to do.
    assert delivered("customer.customer.created").count == 0


def test_a_card_corrected_to_her_number_claims_it_too():
    receive("wamid.1", "34600111222")
    ana = card("Ana López", "")
    run("customer.customer.update", {"id": str(ana.id), "phone": "+34 600 111 222"})
    assert delivered("customer.customer.updated").count == 1
    assert conversation().customer_id == ana.id


def test_a_number_on_two_cards_claims_nothing_and_a_link_somebody_made_is_kept():
    receive("wamid.1", "34600111222")
    card("Ana López", "600111222")
    card("Ana L.", "600111222")
    assert delivered("customer.customer.created").count == 0
    assert conversation().customer_id is None
    marta = card("Marta", "699000111")
    run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(conversation().id), "customer_id": str(marta.id)},
    )
    run("customer.customer.update", {"id": str(marta.id), "notes": "VIP"})
    delivered("customer.customer.updated")
    assert conversation().customer_id == marta.id


def test_merging_two_cards_moves_her_conversations_to_the_one_that_stays():
    receive("wamid.1", "34600111222")
    duplicate = card("Ana L.", "600111222")
    delivered("customer.customer.created")
    survivor = card("Ana López", "699000111")
    run(
        "customer.customer.merge",
        {"id": str(survivor.id), "absorbed_id": str(duplicate.id)},
    )
    assert delivered("customer.customer.merged").count == 1
    assert conversation().customer_id == survivor.id
    assert delivered("customer.customer.merged").count == 0


def test_erasing_her_card_erases_her_conversations_and_frees_her_number():
    receive("wamid.1", "34600111222", text="Mi dirección es…")
    receive("wamid.2", "34600999888")
    ana = card("Ana López", "600111222")
    delivered("customer.customer.created")
    run("customer.customer.erase", {"id": str(ana.id), "reason": "Asked by email"})
    assert delivered("customer.customer.erased").count == 1
    erased = Conversation.objects.get(erased_at__isnull=False)
    assert (erased.phone, erased.contact_name, erased.customer_id) == ("", "", None)
    assert Message.objects.get(wa_message_id="wamid.1").body == ""
    # The other person is untouched; a second delivery changes nothing.
    assert (
        Conversation.objects.filter(erased_at__isnull=True).get().phone
        == "+34600999888"
    )
    assert delivered("customer.customer.erased").count == 0
    # If she writes again: a new conversation, new consent.
    receive("wamid.3", "34600111222")
    assert Conversation.objects.filter(erased_at__isnull=True).count() == 2


def test_a_deleted_card_lets_her_conversation_go_and_another_card_of_the_number_claims_it():
    receive("wamid.1", "34600111222")
    old = card("Ana López", "600111222")
    delivered("customer.customer.created")
    assert conversation().customer_id == old.id
    run("customer.customer.delete", {"id": str(old.id)})
    assert delivered("customer.customer.deleted").count == 1
    assert conversation().customer_id is None
    new = card("Ana L.", "600111222")
    assert delivered("customer.customer.created").count == 1
    assert conversation().customer_id == new.id


def test_a_card_deleted_while_nobody_reacted_counts_as_no_card_when_she_writes():
    receive("wamid.1", "34600111222")
    old = card("Ana López", "600111222")
    delivered("customer.customer.created")
    run("customer.customer.delete", {"id": str(old.id)})  # its event not handed over yet
    new = card("Ana L.", "600111222")
    receive("wamid.2", "34600111222")
    assert conversation().customer_id == new.id
    detail = run("whatsapp_inbox.conversation.detail", {"id": str(conversation().id)})
    assert (detail.customer_id, detail.customer_name) == (new.id, "Ana L.")
