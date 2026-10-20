"""Several deliveries and people at once: real sessions in threads, real row locks.

The same WhatsApp message delivered twice at the same time is one message and one unread; two first
messages of a new number at once open one conversation; two people pressing «Assign to me» at once:
one gets it, the other is told who has it (WORKBOOK «Reglas que no se rompen»).
"""

import threading
import uuid

import httpx
import pytest
import respx
from django.db import connection
from live.errors import Conflict, OperationError

from apps.customer.models import Customer
from apps.customer.tests.conftest import card_deleted_on_screen, delete_card, reads
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, card, connect, ctx_for, receive, run, system, template

pytestmark = pytest.mark.django_db(transaction=True)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_the_same_message_twice_at_once_is_one_message_and_one_unread():
    results = at_once(*[lambda: receive("wamid.SAME", "34600111222") for _ in range(4)])
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(r.created for r in results) == [False, False, False, True]
    assert Message.objects.count() == 1
    assert Conversation.objects.get().unread_count == 1


def test_two_first_messages_of_a_number_at_once_open_one_conversation():
    results = at_once(
        lambda: receive("wamid.A", "34600111222"),
        lambda: receive("wamid.B", "34600111222"),
        lambda: receive("wamid.C", "+34600111222"),
    )
    assert not [r for r in results if isinstance(r, Exception)], results
    assert Conversation.objects.count() == 1
    assert Conversation.objects.get().unread_count == 3
    assert Message.objects.count() == 3


def test_two_people_taking_the_same_conversation_at_once(make_user):
    receive("wamid.1")
    conversation = str(Conversation.objects.get().id)
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")

    def take(person):
        return lambda: run(
            "whatsapp_inbox.conversation.assign",
            {"id": conversation, "assignee": "me", "only_if_unassigned": True},
            ctx_for("hub_employee", actor=person),
        )

    results = at_once(take(luis), take(marta))
    won = [r for r in results if not isinstance(r, Exception)]
    lost = [r for r in results if isinstance(r, Exception)]
    assert len(won) == 1 and len(lost) == 1
    assert (
        isinstance(lost[0], Conflict)
        and lost[0].code == "whatsapp_inbox.already_assigned"
    )
    assert Conversation.objects.get().assigned_to_id == won[0].assigned_to_id


SEND = "http://saas.test/internal/whatsapp/send"


def ready() -> str:
    connect()
    receive("wamid.IN", sent_at=NOW.isoformat())
    return str(Conversation.objects.get().id)


@respx.mock
def test_no_lock_is_held_while_erplora_answers():
    """A slow erplora.com never blocks the conversation: «mark read» goes through mid-send."""
    conversation = ready()
    receive("wamid.IN2", sent_at=NOW.isoformat())
    in_http, release = threading.Event(), threading.Event()

    def slow(request):
        in_http.set()
        release.wait(10)
        return httpx.Response(200, json={"wa_message_id": "wamid.SLOW"})

    respx.post(SEND).mock(side_effect=slow)
    outcome: dict = {}

    def sender():
        try:
            outcome["sent"] = run(
                "whatsapp_inbox.message.send",
                {"id": conversation, "text": "Hola", "client_message_id": str(uuid.uuid7())},
            )
        except Exception as error:  # reported by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=sender)
    thread.start()
    try:
        assert in_http.wait(10), "the send never reached erplora.com"
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '2s'")
        read = run("whatsapp_inbox.conversation.mark_read", {"id": conversation})
        assert read.unread_count == 0
    finally:
        release.set()
        thread.join(30)
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = 0")
    assert "error" not in outcome, outcome
    assert Message.objects.get(pk=outcome["sent"].id).status == "sent"


@respx.mock
def test_the_same_key_twice_at_once_is_one_message_sent_once():
    conversation = ready()
    route = respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.ONCE"}))
    key = str(uuid.uuid7())
    payload = {"id": conversation, "text": "Hola", "client_message_id": key}
    results = at_once(*[lambda: run("whatsapp_inbox.message.send", payload) for _ in range(3)])
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len({r.id for r in results}) == 1
    assert Message.objects.filter(direction="outbound").count() == 1
    assert route.call_count == 1


# ── The Hub admin's «Delete» of a card while a conversation is joined to it ───────────────────────
#
# Joining a conversation to a card (by hand, by the number of a message received or sent, when a card claims its
# number's conversations, when a merge moves them to the card that stays, when a deleted card's go to the other
# card of the number) finds the card and then writes the link. The Hub admin's «Delete» of that card between the
# two found no conversation of it to leave without the card and deleted it: the link then failed at its COMMIT
# (an IntegrityError, a 500; a message lost, a reaction retried for ever). The card is locked before the
# conversation, as the deletion takes them: the deletion waits and then leaves the conversation without the card;
# a join that comes second waits for the deletion and finds no card to join.

HOW = ["page", "list"]


def links(nth: int = 1):
    """Whether a statement is the ``nth`` one of this session that writes a conversation's card."""
    seen = []

    def accepts(sql: str) -> bool:
        if sql.lstrip().startswith('UPDATE "whatsapp_inbox_conversation" SET "customer_id"'):
            seen.append(sql)
        return len(seen) == nth

    return accepts


def card_of(name: str = "Ana López", phone: str = "600111222") -> Customer:
    return Customer.objects.get(pk=card(name, phone).id)


def _by_hand(ana):
    receive("wamid.0", "34699000111")
    conversation = Conversation.objects.get()
    return lambda: run(
        "whatsapp_inbox.conversation.link_customer", {"id": str(conversation.id), "customer_id": str(ana.id)}
    )


def _received(ana):
    return lambda: receive("wamid.1", "34600111222")


def _sent(ana):
    connect(templates=[template("recordatorio")])
    respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    payload = {
        "to": "600 111 222",
        "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]},
        "client_message_id": str(uuid.uuid7()),
    }
    return lambda: run("whatsapp_inbox.message.send", payload)


def _claimed(ana):
    receive("wamid.0", "34600111222")
    Conversation.objects.update(customer=None)
    return lambda: system("whatsapp_inbox.conversation.claim_for_customer", {"id": str(ana.id)})


def _moved(ana):
    receive("wamid.0", "34600111222")
    old = card_of("Ana L.", "699000111")
    Conversation.objects.update(customer=old)
    return lambda: system(
        "whatsapp_inbox.conversation.move_customer", {"id": str(ana.id), "absorbed_id": str(old.id)}
    )


def _released(ana):
    receive("wamid.0", "34600111222")
    old = card_of("Ana L.", "600111222")
    Conversation.objects.update(customer=old)
    Customer.objects.filter(pk=old.pk).update(deleted_at=NOW)
    return lambda: system("whatsapp_inbox.conversation.release_customer", {"id": str(old.id)})


#: Each way a conversation is joined to a card, and which write of the card it is (a release first takes the
#: deleted card off).
JOINS = {
    "by hand": (_by_hand, 1),
    "message received": (_received, 1),
    "message sent": (_sent, 1),
    "claimed": (_claimed, 1),
    "merge": (_moved, 1),
    "release": (_released, 2),
}


@respx.mock
@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("join", sorted(JOINS))
def test_the_hub_admin_deleting_a_card_a_conversation_is_joined_to_meanwhile_leaves_it_without(join, how):
    ana = card_of()
    make, nth = JOINS[join]
    joining = make(ana)
    with card_deleted_on_screen(ana, how, links(nth)) as answers:
        joining()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Customer.objects.filter(pk=ana.pk).exists()
    assert not Conversation.objects.filter(customer_id=ana.pk).exists()


#: The joins that find no card to join when the deletion came first, and what they answer then.
JOINS_FIRST_DELETED = {
    "by hand": "customer.customer_unavailable",
    "message received": None,
    "claimed": None,
}


@respx.mock
@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("join", sorted(JOINS_FIRST_DELETED))
def test_a_join_to_a_card_the_hub_admin_deletes_first_joins_nothing(join, how):
    ana = card_of()
    joining = JOINS[join][0](ana)
    refusal = JOINS_FIRST_DELETED[join]
    with card_deleted_on_screen(ana, how, reads("customer_customer")) as answers:
        try:
            joining()
        except OperationError as error:
            assert (error.status, error.code) == (404, refusal)
        else:
            assert refusal is None
    [answer] = answers
    assert answer.status_code == 302
    assert not Customer.objects.filter(pk=ana.pk).exists()
    assert not Conversation.objects.filter(customer_id=ana.pk).exists()


@pytest.mark.parametrize("how", HOW)
def test_a_merge_into_a_card_the_hub_admin_deleted_moves_no_conversation(how):
    ana = card_of()
    move = _moved(ana)
    old = Conversation.objects.get().customer_id
    assert delete_card(ana, how).status_code == 302
    assert move().count == 0
    assert Conversation.objects.get().customer_id == old


# The Hub admin's «Delete selected» of the card a conversation is joined to and of the card it is being joined to
# instead: the deletion locks both cards and then leaves the conversation without them. A join that locked the
# conversation first and the new card then (the other way round) waited for the deletion while the deletion waited
# for it (a deadlock, a 500). Card first, the join waits for the deletion and finds its card gone.


def _rejoined_by_hand(old, ana):
    receive("wamid.0", "34699000111")
    conversation = Conversation.objects.get()
    Conversation.objects.update(customer=old)
    return lambda: run(
        "whatsapp_inbox.conversation.link_customer", {"id": str(conversation.id), "customer_id": str(ana.id)}
    )


def _rejoined_by_a_message(old, ana):
    receive("wamid.0", "34600111222")
    Conversation.objects.update(customer=old)
    Customer.objects.filter(pk=old.pk).update(deleted_at=NOW)
    return lambda: receive("wamid.1", "34600111222")


#: A join of a conversation from one card to another, and what it answers when both cards are gone.
REJOINS = {"by hand": (_rejoined_by_hand, "customer.customer_unavailable"), "message received": (_rejoined_by_a_message, None)}


@pytest.mark.parametrize("join", sorted(REJOINS))
def test_a_join_and_the_hub_admin_deleting_both_its_cards_never_wait_in_a_circle(join):
    ana, old = card_of(), card_of("Ana L.", "699000111")
    make, refusal = REJOINS[join]
    joining = make(old, ana)
    card_locked = lambda sql: 'FROM "customer_customer"' in sql and "FOR UPDATE" in sql  # noqa: E731
    with card_deleted_on_screen(ana, "list", card_locked, also=[old]) as answers:
        try:
            joining()
        except OperationError as error:
            assert (error.status, error.code) == (404, refusal)
        else:
            assert refusal is None
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Customer.objects.filter(pk__in=[ana.pk, old.pk]).exists()
    assert Conversation.objects.get().customer_id is None
