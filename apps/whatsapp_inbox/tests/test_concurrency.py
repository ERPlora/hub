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
from live.errors import Conflict

from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, connect, ctx_for, receive, run

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
