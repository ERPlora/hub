"""WHATSAPP_INBOX-F13 with a plan that includes no WhatsApp messages.

erplora.com sends the plan's ``whatsapp_messages_per_month`` as ``monthly_limit``, and 0 means the plan includes
none (ADR-0474: there is no «unlimited», and erplora.com refuses every send with ``whatsapp.cap_reached``). So the
month is spent from its first message, the inbox says so and «Send» explains it instead of sending, while what
customers write keeps arriving (F03 step 6).
"""

import datetime as dt
import uuid

import httpx
import pytest
import respx
from django.utils.translation import override
from live.errors import Conflict

from apps.whatsapp_inbox.models import Channel, Conversation, Message
from apps.whatsapp_inbox.tests.conftest import A, B, NOW, connect, ctx_for, receive, run, system

pytestmark = pytest.mark.django_db

SEND = "http://saas.test/internal/whatsapp/send"
#: What erplora.com sends for a plan without WhatsApp messages, before any is sent this month.
NONE = {"monthly_limit": 0, "monthly_usage": 0, "usage_month": "2026-10"}


def conversation() -> Conversation:
    return Conversation.objects.get(erased_at__isnull=True)


def test_a_plan_without_messages_is_spent_from_the_first_message_of_every_month():
    row = Channel(synced_at=NOW, **NONE)
    assert row.cap_reached("2026-10") is True
    # Another month brings none either, also before erplora.com speaks of it.
    assert row.cap_reached("2026-11") is True


def test_before_erplora_speaks_no_cap_is_assumed():
    # The row's 0 is only its default until erplora.com sends the plan's figure: nothing is known yet.
    assert Channel(**NONE).cap_reached("2026-10") is False
    empty = run("whatsapp_inbox.channel.get", {})
    assert (empty.monthly_limit, empty.cap_reached, empty.synced_at) == (0, False, None)


def test_the_inbox_says_it_and_send_explains_it_instead_of_sending():
    connect(**NONE)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    detail = run("whatsapp_inbox.conversation.detail", {"id": str(conversation().id)})
    assert (detail.window_open, detail.can_send, detail.send_blocked) == (True, False, "cap_reached")
    assert run("whatsapp_inbox.conversation.summary", {}).cap_reached is True
    channel = run("whatsapp_inbox.channel.get", {})
    assert (channel.monthly_limit, channel.monthly_usage, channel.cap_reached) == (0, 0, True)


@respx.mock
def test_a_send_is_refused_and_nothing_reaches_erplora():
    connect(**NONE)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    route = respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    with pytest.raises(Conflict) as excinfo:
        run(
            "whatsapp_inbox.message.send",
            {"id": str(conversation().id), "text": "Hola", "client_message_id": str(uuid.uuid7())},
        )
    assert excinfo.value.code == "whatsapp_inbox.cap_reached"
    assert route.call_count == 0
    assert not Message.objects.filter(direction=Message.Direction.OUTBOUND).exists()


def refusal(language: str = "en") -> Conflict:
    """What «Send» (the API, the assistant) answers in this conversation, in the request's ``language``."""
    with override(language), pytest.raises(Conflict) as excinfo:
        run(
            "whatsapp_inbox.message.send",
            {"id": str(conversation().id), "text": "Hola", "client_message_id": str(uuid.uuid7())},
        )
    return excinfo.value


def test_the_refusal_says_the_plan_includes_none_never_until_next_month():
    connect(**NONE)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    # The published code stays: erplora.com refuses a plan without messages with its own cap_reached too.
    english, spanish = refusal("en"), refusal("es")
    assert (english.code, spanish.code) == ("whatsapp_inbox.cap_reached", "whatsapp_inbox.cap_reached")
    assert "does not include WhatsApp messages" in str(english)
    assert "next month" not in str(english)
    assert "no incluye mensajes de WhatsApp" in str(spanish)
    assert "mes que viene" not in str(spanish)


def test_a_spent_month_still_says_until_next_month():
    connect(monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    spent = refusal()
    assert spent.code == "whatsapp_inbox.cap_reached"
    assert "next month" in str(spent)
    assert "does not include" not in str(spent)


def test_what_customers_write_still_arrives():
    connect(**NONE)
    first = receive("wamid.1", text="Hola")
    second = receive("wamid.2", text="¿Tenéis hora el viernes?")
    assert (first.created, second.created) == (True, True)
    row = conversation()
    assert (row.unread_count, row.last_message_preview) == (2, "¿Tenéis hora el viernes?")


def test_each_business_has_its_own_plan():
    connect(**NONE)
    system(
        "whatsapp_inbox.channel.sync",
        {"version": 1, "status": "connected", "phone_number": "+34910000001", "monthly_limit": 150},
        B,
    )
    a = run("whatsapp_inbox.channel.get", {}, ctx_for(scope=A))
    b = run("whatsapp_inbox.channel.get", {}, ctx_for(scope=B))
    assert (a.cap_reached, b.cap_reached) == (True, False)


def test_the_channel_says_where_the_plan_is_upgraded(settings):
    assert run("whatsapp_inbox.channel.get", {}).plans_url == "https://erplora.com/dashboard/store/plans"
    settings.SAAS_URL = "https://erplora.com/"
    assert run("whatsapp_inbox.channel.get", {}).plans_url == "https://erplora.com/dashboard/store/plans"
    # A server not linked to erplora.com has nowhere to send the owner.
    settings.SAAS_URL = ""
    assert run("whatsapp_inbox.channel.get", {}).plans_url == ""
