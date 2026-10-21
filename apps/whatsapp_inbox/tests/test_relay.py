"""The inbox's reactions to Customers, end to end through the worker's real outbox relay (WHATSAPP_INBOX-F04,
F11, F12, F37; ``base/relay.py``, which delivers in phase 1 since hub#105).

Customers' own operations write the cards and record their events; the worker's loop takes them and runs the
inbox's reaction as the system, once. Nothing is called by hand: before the tick nothing has changed, after it
the conversation follows the card. erplora.com's erasure door is the only thing ``respx`` stands in for.
"""

import datetime as dt
import threading

import httpx
import pytest
import respx
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.tests.conftest import ctx_for, receive, run
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

pytestmark = pytest.mark.django_db

ERASE = "http://saas.test/internal/whatsapp/erase"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


@pytest.fixture
def tick(monkeypatch, django_capture_on_commit_callbacks):
    """One turn of the worker's real loop, without the SaaS's catalogue and, inside the test's transaction,
    without releasing its connection; what the reactions leave for after their COMMIT runs too."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    now = timezone.now()

    def run_once() -> None:
        stop = threading.Event()

        def wait(seconds: float) -> bool:
            stop.set()
            return True

        with django_capture_on_commit_callbacks(execute=True):
            assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now + dt.timedelta(seconds=1)) == 0

    return run_once


def owner():
    return ctx_for("hub_owner")


def conversation() -> Conversation:
    return Conversation.objects.get()


def card(name: str = "Ana López", phone: str = "600111222"):
    return run("customer.customer.create", {"name": name, "phone": phone}, owner())


def deliveries(app: str = "whatsapp_inbox") -> int:
    return EventDelivery.objects.filter(app_label=app, status=EventDelivery.Status.DELIVERED).count()


def test_a_card_made_with_her_number_joins_her_conversation_through_the_relay(tick):
    """F04: she wrote first; the card made afterwards claims her conversation, once."""
    receive("wamid.1")
    assert conversation().customer_id is None
    ana = card()
    assert conversation().customer_id is None  # nothing in line: the relay does it
    tick()
    assert conversation().customer_id == ana.id
    assert deliveries() >= 1
    tick()  # again: nothing changes, nothing is delivered twice
    assert conversation().customer_id == ana.id


def test_a_card_corrected_to_her_number_joins_her_conversation(tick):
    receive("wamid.1")
    ana = card(phone="600999999")
    tick()
    assert conversation().customer_id is None
    run("customer.customer.update", {"id": str(ana.id), "phone": "+34 600 111 222"}, owner())
    tick()
    assert conversation().customer_id == ana.id


def test_merging_two_cards_moves_her_conversation_to_the_one_that_stays(tick):
    """F12."""
    receive("wamid.1")
    duplicate = card("Ana L.")
    tick()
    assert conversation().customer_id == duplicate.id
    stays = card("Ana López", phone="600222333")
    run("customer.customer.merge", {"id": str(stays.id), "absorbed_id": str(duplicate.id)}, owner())
    tick()
    assert conversation().customer_id == stays.id


@respx.mock
def test_erasing_her_card_erases_her_conversations_here_and_asks_erplora_to_forget(tick):
    """F11: the card's erasure reaches the inbox by the relay; the number is blanked at once and erplora.com
    is asked to forget it after the reaction's COMMIT."""
    route = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    receive("wamid.1")
    ana = card()
    tick()
    run("customer.customer.erase", {"id": str(ana.id), "reason": "Lo pidió por WhatsApp"}, owner())
    assert conversation().erased_at is None
    tick()
    erased = conversation()
    assert (erased.phone, erased.contact_name, erased.customer_id, erased.erased_at is not None) == ("", "", None, True)
    assert route.call_count == 1
    assert erased.erase_status == "done" and erased.erase_phone == ""


def test_deleting_her_card_lets_another_card_of_her_number_claim_the_conversation(tick):
    receive("wamid.1")
    first = card()
    tick()
    assert conversation().customer_id == first.id
    run("customer.customer.delete", {"id": str(first.id)}, owner())
    second = card("Ana López Ruiz")
    tick()
    assert conversation().customer_id == second.id


def test_a_card_made_from_the_conversation_is_joined_once_and_the_relay_changes_nothing(tick):
    """F37: «Create card» joins it in its own transaction; the card's creation, relayed, finds it joined."""
    out = receive("wamid.1")
    joined = run("whatsapp_inbox.conversation.link_customer", {"id": str(out.conversation_id), "create": True}, owner())
    before = conversation().customer_id
    assert joined.customer_id == before is not None
    tick()
    assert conversation().customer_id == before
