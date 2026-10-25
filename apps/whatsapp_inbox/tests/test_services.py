"""Write operations of the WhatsApp inbox (WHATSAPP_INBOX-F03…F37), against the real Customers app.

The cases of the product's tests are kept (one row per WhatsApp message, the history that does not
count as unread, the echo of the owner's phone, the link by number that only fills, the erasure that
frees the number…); sending goes through ``respx`` as the transport to erplora.com only.
"""

import datetime as dt
import json
import uuid

import httpx
import pydantic
import pytest
import respx
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.customer.models import Customer
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import (
    A,
    B,
    NOW,
    card,
    connect,
    ctx_for,
    receive,
    run,
    system,
    template,
)

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
SEND = f"{SAAS}/internal/whatsapp/send"


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_INTERNAL_URL = SAAS
    settings.INTERNAL_SHARED_SECRET = "s3cret"


def events(name: str) -> list[dict]:
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


def conv() -> Conversation:
    return Conversation.objects.get(erased_at__isnull=True)


# ── WHATSAPP_INBOX-F03 Receive a message ────────────────────────────────────────────────────────


def test_the_first_message_opens_a_conversation_keyed_by_the_international_number():
    out = receive("wamid.1", "34600111222", contact_name="Ana")
    c = conv()
    assert (c.phone, c.contact_name, c.status, c.unread_count) == (
        "+34600111222",
        "Ana",
        "open",
        1,
    )
    assert (c.last_message_at, c.last_inbound_at, c.last_message_direction) == (
        NOW,
        NOW,
        "inbound",
    )
    assert c.last_message_preview == "Hola, ¿tenéis hora mañana?"
    message = Message.objects.get()
    assert (
        message.direction,
        message.origin,
        message.source,
        message.status,
        message.kind,
    ) == (
        "inbound",
        "customer",
        "live",
        "received",
        "text",
    )
    assert (out.id, out.conversation_id, out.created) == (message.id, c.id, True)
    assert events("whatsapp_inbox.message.received") == [
        {
            "id": str(message.id),
            "conversation_id": str(c.id),
            "direction": "inbound",
            # It answers nothing the Hub sent (WHATSAPP_INBOX-F38): empty, never absent.
            "reply_to_message_id": None,
            "reply_id": "",
        }
    ]


def test_a_message_delivered_twice_is_one_message_and_one_unread():
    receive("wamid.DUP")
    again = receive("wamid.DUP", text="otro texto")
    assert again.created is False
    assert Message.objects.count() == 1
    assert Message.objects.get().body == "Hola, ¿tenéis hora mañana?"
    assert conv().unread_count == 1
    assert len(events("whatsapp_inbox.message.received")) == 1


def test_the_same_number_in_any_format_is_one_conversation():
    receive("wamid.1", "34600111222")
    receive("wamid.2", "+34600111222")
    assert Conversation.objects.count() == 1
    assert conv().unread_count == 2


def test_another_country_s_prefix_is_another_person():
    receive("wamid.1", "34600111222")
    receive("wamid.2", "33600111222")
    assert set(Conversation.objects.values_list("phone", flat=True)) == {
        "+34600111222",
        "+33600111222",
    }


def test_an_unreadable_number_is_a_422_on_from():
    # A malformed one never reaches the operation (the schema refuses it); a well-formed number of no
    # country is refused by the operation.
    with pytest.raises(pydantic.ValidationError):
        receive("wamid.1", "12")
    with pytest.raises(InvalidPayload) as excinfo:
        receive("wamid.1", "999123456789")
    assert set(excinfo.value.fields) == {"from"}
    assert Conversation.objects.count() == 0


def test_history_keeps_its_time_and_does_not_count_as_unread():
    receive("wamid.1", sent_at=(NOW - dt.timedelta(hours=1)).isoformat())
    receive(
        "wamid.0",
        source="history",
        text="De marzo",
        sent_at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC).isoformat(),
    )
    c = conv()
    assert c.unread_count == 1
    # An older message never becomes «the last one».
    assert c.last_message_at == NOW - dt.timedelta(hours=1)
    assert c.last_message_preview == "Hola, ¿tenéis hora mañana?"
    old = Message.objects.get(wa_message_id="wamid.0")
    assert (old.source, old.sent_at) == (
        "history",
        dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
    )


def test_a_history_placeholder_is_completed_in_place():
    receive("wamid.H", source="history", type="media_placeholder", text="")
    receive(
        "wamid.H",
        source="history",
        type="image",
        text="",
        media={
            "url": "https://erplora.com/whatsapp/media/h",
            "mime_type": "image/jpeg",
            "caption": "Mi pelo",
        },
        payload={"id": "wamid.H", "type": "image"},
    )
    message = Message.objects.get()
    assert (
        message.kind,
        message.media_url,
        message.media_caption,
        message.payload,
    ) == (
        "image",
        "https://erplora.com/whatsapp/media/h",
        "Mi pelo",
        {"id": "wamid.H", "type": "image"},
    )
    assert conv().unread_count == 0


def test_a_live_message_is_never_rewritten_after_the_fact():
    receive("wamid.L", type="media_placeholder", text="")
    receive("wamid.L", type="image", media={"url": "https://erplora.com/m"})
    assert Message.objects.get().kind == "media_placeholder"


def test_the_owner_s_reply_from_the_phone_is_the_business_s_message_and_not_unread():
    receive("wamid.1", sent_at=(NOW - dt.timedelta(minutes=5)).isoformat())
    receive("wamid.ECHO", direction="outbound", text="Sí, a las 10")
    c = conv()
    assert c.unread_count == 1
    assert c.last_inbound_at == NOW - dt.timedelta(minutes=5)
    assert (c.last_message_direction, c.last_message_preview) == (
        "outbound",
        "Sí, a las 10",
    )
    echo = Message.objects.get(wa_message_id="wamid.ECHO")
    assert (echo.direction, echo.origin, echo.status) == (
        "outbound",
        "phone_app",
        "sent",
    )


@pytest.mark.parametrize("status", ["pending", "closed"])
def test_the_customer_writing_again_reopens_the_conversation(status):
    receive("wamid.1")
    Conversation.objects.update(status=status)
    receive(
        "wamid.0", source="history", sent_at=(NOW - dt.timedelta(days=9)).isoformat()
    )
    assert conv().status == status  # the past does not reopen anything
    receive("wamid.2")
    assert conv().status == "open"


def test_an_attachment_is_kept_by_its_url_and_named_in_the_preview():
    receive(
        "wamid.P",
        type="document",
        text="",
        media={
            "url": "https://erplora.com/whatsapp/media/doc",
            "mime_type": "application/pdf",
            "filename": "presupuesto.pdf",
        },
    )
    message = Message.objects.get()
    assert (message.media_url, message.media_mime_type, message.media_filename) == (
        "https://erplora.com/whatsapp/media/doc",
        "application/pdf",
        "presupuesto.pdf",
    )
    assert (conv().last_message_preview, conv().last_message_kind) == ("presupuesto.pdf", "document")


def test_a_message_without_text_keeps_its_type_for_the_inbox_to_name():
    receive("wamid.L", type="location", text="")
    assert (conv().last_message_preview, conv().last_message_kind) == ("", "location")


def test_a_reaction_is_kept_without_counting_nor_becoming_the_last_message():
    receive("wamid.1", text="¿Mañana a las 10?")
    out = receive("wamid.R", type="reaction", text="👍", reply_to="wamid.1")
    c = conv()
    assert (c.unread_count, c.last_message_preview, c.last_message_kind) == (1, "¿Mañana a las 10?", "text")
    reaction = Message.objects.get(pk=out.id)
    assert (reaction.kind, reaction.body, reaction.reply_to) == ("reaction", "👍", "wamid.1")


def test_receiving_is_the_system_s_alone():
    from live.operations import get

    op = get("whatsapp_inbox.message.receive")
    for role in ("hub_owner", "hub_admin", "hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            op(
                ctx_for(role),
                op.input.model_validate({"wa_message_id": "w", "from": "34600111222"}),
            )


def test_after_an_erasure_the_number_starts_a_new_conversation():
    receive("wamid.1")
    first = conv()
    run("whatsapp_inbox.conversation.erase", {"id": str(first.id)})
    receive("wamid.2")
    assert conv().id != first.id
    assert conv().unread_count == 1


# ── WHATSAPP_INBOX-F04 Recognise the customer by her number ─────────────────────────────────────


def test_a_number_on_exactly_one_card_joins_the_conversation_to_it():
    ana = card("Ana López", "600 111 222")
    receive("wamid.1", "34600111222")
    assert conv().customer_id == ana.id
    assert events("whatsapp_inbox.conversation.customer_linked") == [
        {"id": str(conv().id), "customer_id": str(ana.id)}
    ]


def test_a_number_that_keeps_its_leading_zero_abroad_is_recognised():
    """gh:whatsapp_inbox#201: an Italian landline keeps its 0 after +39, on the card and on WhatsApp."""
    gianni = card("Gianni Rossi", "+39 06 1234 5678")
    receive("wamid.1", "390612345678")
    assert (conv().phone, conv().customer_id) == ("+390612345678", gianni.id)


def test_two_cards_with_the_number_join_it_to_nobody():
    card("Ana López", "600111222")
    card("Ana L.", "+34 600 111 222")
    receive("wamid.1", "34600111222")
    assert conv().customer_id is None


def test_the_link_somebody_made_is_kept():
    other = card("Marta", "600999888")
    card("Ana López", "600111222")
    receive("wamid.1", "34600111222")
    run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(conv().id), "customer_id": str(other.id)},
    )
    receive("wamid.2", "34600111222")
    assert conv().customer_id == other.id


# ── WHATSAPP_INBOX-F34 Delivery statuses ────────────────────────────────────────────────────────


def sent_message(wa_id="wamid.OUT") -> Message:
    receive("wamid.IN")
    return Message.objects.create(
        conversation=conv(),
        direction="outbound",
        origin="hub",
        status="sent",
        wa_message_id=wa_id,
        sent_at=NOW,
    )


def status(wa_id, value, **fields):
    return system(
        "whatsapp_inbox.message.update_status",
        {"wa_message_id": wa_id, "status": value, **fields},
    )


def test_a_status_only_moves_forward():
    message = sent_message()
    assert status("wamid.OUT", "delivered").model_dump() == {
        "updated": True,
        "status": "delivered",
    }
    assert status("wamid.OUT", "read").status == "read"
    late = status("wamid.OUT", "delivered")
    assert (late.updated, late.status) == (False, "read")
    assert (
        status("wamid.OUT", "failed", error={"code": "131047", "message": "x"}).updated
        is False
    )
    message.refresh_from_db()
    assert message.status == "read"
    assert len(events("whatsapp_inbox.message.status_changed")) == 2


def test_failed_replaces_sent_or_delivered_with_meta_s_reason():
    sent_message()
    status("wamid.OUT", "delivered")
    out = status(
        "wamid.OUT",
        "failed",
        error={"code": "131047", "message": "More than 24 hours"},
        status_at=NOW.isoformat(),
    )
    assert out.status == "failed"
    message = Message.objects.get(wa_message_id="wamid.OUT")
    assert (message.error_code, message.error_message, message.status_at) == (
        "131047",
        "More than 24 hours",
        NOW,
    )


def test_an_unknown_message_changes_nothing():
    assert status("wamid.NOBODY", "read").model_dump() == {
        "updated": False,
        "status": None,
    }


# ── WHATSAPP_INBOX-F13, F27, F28 The channel and its templates ─────────────────────────────────


def test_the_channel_follows_erplora_s_newest_version():
    assert connect(version=2).applied is True
    channel = Channel.objects.get()
    assert (
        channel.status,
        channel.phone_number,
        channel.monthly_limit,
        channel.monthly_usage,
        channel.version,
    ) == (
        "connected",
        "+34910000000",
        150,
        10,
        2,
    )
    assert channel.synced_at == NOW
    stale = connect(version=2, status="reconnect_needed")
    assert stale.model_dump() == {"applied": False, "version": 2}
    assert connect(version=1, status="not_connected").applied is False
    assert Channel.objects.get().status == "connected"
    assert connect(version=3, status="reconnect_needed").applied is True
    assert Channel.objects.get().status == "reconnect_needed"
    assert len(events("whatsapp_inbox.channel.synced")) == 2


def channel_of(scope):
    return run("whatsapp_inbox.channel.get", {}, ctx_for(scope=scope))


def test_each_business_keeps_its_own_number_and_its_own_version():
    # The row was one for every business: B's newer photo said «not connected» for A too.
    assert connect(version=50).applied is True
    b = {"version": 120, "status": "not_connected", "phone_number": "", "display_name": ""}
    assert system("whatsapp_inbox.channel.sync", b, B).applied is True

    a_now, b_now = channel_of(A), channel_of(B)
    assert (a_now.status, a_now.phone_number, a_now.monthly_limit) == ("connected", "+34910000000", 150)
    assert (b_now.status, b_now.phone_number, b_now.monthly_limit) == ("not_connected", "", 0)
    # Each version is its own business's: A's 60 is newer than A's 50, whatever B's is.
    assert connect(version=60, status="reconnect_needed").applied is True
    assert system("whatsapp_inbox.channel.sync", {**b, "version": 110}, B).applied is False
    assert (channel_of(A).status, channel_of(B).status) == ("reconnect_needed", "not_connected")
    assert set(Channel.objects.values_list("host", "version")) == {("a", 60), ("b", 120)}


def test_only_the_business_with_its_number_connected_may_send_and_its_month_is_its_own():
    connect(version=1, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    receive("wamid.1", "34600111222")
    ref = {"id": str(conv().id)}
    a = run("whatsapp_inbox.conversation.detail", ref, ctx_for(scope=A))
    b = run("whatsapp_inbox.conversation.detail", ref, ctx_for(scope=B))
    assert (a.send_blocked, b.send_blocked) == ("cap_reached", "not_connected")
    a_month = run("whatsapp_inbox.conversation.summary", {}, ctx_for(scope=A))
    b_month = run("whatsapp_inbox.conversation.summary", {}, ctx_for(scope=B))
    assert (a_month.cap_reached, b_month.cap_reached) == (True, False)


def test_each_business_s_photo_keeps_its_own_number(client, settings):
    # Two businesses with the inbox on: A's photo v50 says connected, B's v120 not connected.
    from base.models import Hub
    from base.tests.test_internal import SECRET, signed

    settings.INTERNAL_SHARED_SECRET, settings.INTERNAL_SHARED_SECRET_PREVIOUS = SECRET, ""
    # The registry has the local hubs ``a`` and ``b`` (the root conftest, as ``seed_local_hubs``).
    a_id, b_id = (str(Hub.objects.get(slug=slug).id) for slug in ("a", "b"))
    block = {"status": "connected", "phone_number": "+34910000000", "display_name": "Ana", "version": 1}

    def photo(hub_id, slug, version, **whatsapp):
        body = {"hub_id": hub_id, "slug": slug, "version": version, "status": "active", "whatsapp": {**block, **whatsapp}}
        return signed(client, "put", f"/internal/hubs/{hub_id}/state", body)

    assert photo(a_id, "a", 50).json() == {"applied": True, "version": 50}
    assert photo(b_id, "b", 120, status="not_connected", phone_number="", display_name="").json()["applied"] is True

    assert (channel_of(A).status, channel_of(A).phone_number) == ("connected", "+34910000000")
    assert (channel_of(B).status, channel_of(B).phone_number) == ("not_connected", "")


def test_templates_are_replaced_by_the_list_and_the_missing_ones_stay_deleted():
    connect(
        version=1,
        templates=[template("recordatorio"), template("promo", category="MARKETING")],
    )
    assert set(Template.objects.values_list("name", "status")) == {
        ("recordatorio", "APPROVED"),
        ("promo", "APPROVED"),
    }
    connect(version=2, templates=[template("recordatorio", status="PAUSED")])
    assert dict(Template.objects.values_list("name", "status")) == {
        "recordatorio": "PAUSED",
        "promo": "DELETED",
    }
    connect(version=3, templates=None)  # null leaves them as they are
    assert Template.objects.count() == 2
    rejected = template("nuevo", status="REJECTED", rejected_reason="INVALID_FORMAT")
    connect(version=4, templates=[rejected])
    assert Template.objects.get(name="nuevo").rejected_reason == "INVALID_FORMAT"


# ── WHATSAPP_INBOX-F32 Reply from the inbox: kept first, handed to erplora.com after the COMMIT ──


def ready(**fields) -> Conversation:
    """A connected number and a conversation whose customer wrote ten minutes ago."""
    connect(
        templates=[
            template("recordatorio"),
            template("promo", category="MARKETING", variables=0, body="¡Oferta!"),
        ]
    )
    receive("wamid.IN", **{"sent_at": (NOW - dt.timedelta(minutes=10)).isoformat(), **fields})
    return conv()


def answering(status=200, body=None, delay=None):
    """erplora.com's sending door: 200 with a new Meta id per message (the first is ``wamid.OUT``)."""
    if body is not None:
        return respx.post(SEND).mock(return_value=httpx.Response(status, json=body))
    sent = iter(range(1, 1000))

    def answer(request):
        number = next(sent)
        return httpx.Response(200, json={"wa_message_id": "wamid.OUT" if number == 1 else f"wamid.OUT{number}"})

    return respx.post(SEND).mock(side_effect=answer)


def key() -> str:
    return str(uuid.uuid7())


def send(payload, ctx=None):
    """``message.send`` with a key of its own unless the payload brings one."""
    return run("whatsapp_inbox.message.send", {"client_message_id": key(), **payload}, ctx)


@pytest.fixture
def delivered(django_capture_on_commit_callbacks):
    """Run a write and then what it left for after its COMMIT (the delivery to erplora.com)."""

    def run_and_deliver(write):
        with django_capture_on_commit_callbacks(execute=True):
            out = write()
        return out

    return run_and_deliver


def stored(out) -> Message:
    return Message.objects.select_related("sent_by").get(pk=out.id)


@respx.mock
def test_a_text_is_kept_queued_and_leaves_only_after_the_commit(make_user, django_capture_on_commit_callbacks):
    c = ready()
    luis = make_user("luis", first_name="Luis", last_name="Gil")
    route = answering()
    k = key()
    with django_capture_on_commit_callbacks(execute=True):
        out = send({"id": str(c.id), "text": "Sí, mañana a las 10", "client_message_id": k}, ctx_for("hub_employee", actor=luis))
        # Inside the operation's transaction nothing has been asked to erplora.com.
        assert route.call_count == 0
        assert (out.status, out.wa_message_id, out.sent_by_name) == ("queued", None, "Luis Gil")
    request = route.calls.last.request
    assert json.loads(request.content) == {"hub": "a", "to": "+34600111222", "type": "text", "text": "Sí, mañana a las 10"}
    assert request.headers["Idempotency-Key"] == k
    message = stored(out)
    assert (message.direction, message.origin, message.status, message.wa_message_id, message.sent_by) == (
        "outbound",
        "hub",
        "sent",
        "wamid.OUT",
        luis,
    )
    c.refresh_from_db()
    assert (c.unread_count, c.last_message_direction, c.last_message_at) == (0, "outbound", NOW)
    assert events("whatsapp_inbox.message.sent") == [{"id": str(message.id), "conversation_id": str(c.id)}]
    assert events("whatsapp_inbox.message.status_changed") == [
        {"id": str(message.id), "conversation_id": str(c.id), "status": "sent"}
    ]


@respx.mock
def test_the_same_key_twice_is_one_message_and_leaves_once(delivered):
    c = ready()
    route = answering()
    k = key()
    first = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    second = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    assert first.id == second.id
    assert route.call_count == 1
    assert Message.objects.filter(direction="outbound").count() == 1


def test_the_key_is_required_so_a_retry_of_the_assistant_never_sends_twice():
    c = ready()
    with pytest.raises(pydantic.ValidationError):
        run("whatsapp_inbox.message.send", {"id": str(c.id), "text": "Hola"})


@respx.mock
def test_after_24_hours_text_is_refused_and_nothing_is_kept():
    c = ready(sent_at=(NOW - dt.timedelta(hours=24, seconds=1)).isoformat())
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.window_closed"
    assert route.call_count == 0
    assert not Message.objects.filter(direction="outbound").exists()


@respx.mock
def test_without_a_connected_number_nothing_is_kept():
    receive("wamid.IN")
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(conv().id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.channel_not_connected"
    # The number is connected from the inbox's Settings (WHATSAPP_INBOX-F01), not in erplora.com.
    assert "in Settings" in excinfo.value.message and "erplora.com" not in excinfo.value.message
    connect(version=1, status="reconnect_needed")
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(conv().id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.channel_not_connected"
    assert route.call_count == 0
    assert not Message.objects.filter(direction="outbound").exists()


def test_without_the_saas_url_nothing_is_kept(settings):
    c = ready()
    settings.SAAS_INTERNAL_URL = ""
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.saas_unconfigured"
    assert not Message.objects.filter(direction="outbound").exists()


@respx.mock
def test_with_the_month_s_messages_spent_nothing_is_kept():
    c = ready()
    connect(version=5, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.cap_reached"
    assert route.call_count == 0


def test_with_the_month_s_messages_spent_what_customers_write_still_arrives():
    """gh:whatsapp_inbox#287, gh:hub#2726: the cap only limits what the business sends."""
    c = ready()
    connect(version=5, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    out = receive("wamid.AFTER", text="¿Tenéis hora el viernes?")
    assert out.created is True and out.conversation_id == c.id
    c.refresh_from_db()
    assert (c.unread_count, c.last_message_preview) == (2, "¿Tenéis hora el viernes?")


@respx.mock
def test_erplora_s_refusal_leaves_the_message_not_delivered_with_its_reason(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.recipient_blocked", "message": "The customer blocked the business."}})
    message = stored(delivered(lambda: send({"id": str(c.id), "text": "Hola"})))
    assert (message.status, message.error_code, message.error_message, message.wa_message_id) == (
        "failed",
        "whatsapp_inbox.send_refused",
        "The customer blocked the business.",
        None,
    )


@respx.mock
def test_erplora_s_cap_refusal_is_the_hub_s_own_cap_reached(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.cap_reached", "message": "Monthly allowance spent."}})
    message = stored(delivered(lambda: send({"id": str(c.id), "text": "Hola"})))
    assert (message.status, message.error_code) == ("failed", "whatsapp_inbox.cap_reached")


@respx.mock
def test_an_expired_permission_is_the_hub_s_reconnect_needed_in_its_own_words(delivered):
    """Meta's 190 (the business's permission expired or withdrawn) reaches the Hub as erplora.com's
    ``whatsapp.reconnect_needed``: the message says the number must be connected again, never Meta's raw words."""
    c = ready()
    raw = "Invalid OAuth access token - Cannot parse access token"
    answering(409, {"error": {"code": "whatsapp.reconnect_needed", "message": raw}})
    message = stored(delivered(lambda: send({"id": str(c.id), "text": "Hola"})))
    assert (message.status, message.error_code, message.error_message, message.wa_message_id) == (
        "failed",
        "whatsapp_inbox.reconnect_needed",
        "WhatsApp's permission for your number expired: connect it again.",
        None,
    )
    assert raw not in message.error_message and "ERPlora" not in message.error_message


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (httpx.ConnectError("refused"), "whatsapp_inbox.saas_unreachable"),
        (httpx.Response(404, json={}), "whatsapp_inbox.saas_unreachable"),
        (httpx.ReadTimeout("slow"), "whatsapp_inbox.send_unknown"),
        (httpx.Response(502, json={}), "whatsapp_inbox.send_unknown"),
    ],
)
@respx.mock
def test_no_final_answer_keeps_it_sending_and_a_retry_uses_the_same_key(delivered, answer, code):
    c = ready()
    route = respx.post(SEND).mock(side_effect=[answer])
    k = key()
    out = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    message = stored(out)
    assert (message.status, message.error_code, message.wa_message_id) == ("sending", code, None)
    # «Not sent · Retry»: the same key, so erplora.com never sends it twice.
    route.side_effect = [httpx.Response(200, json={"wa_message_id": "wamid.LATE"})]
    again = delivered(lambda: run("whatsapp_inbox.message.retry", {"id": str(message.id)}, ctx_for("hub_employee")))
    assert again.id == message.id
    assert route.calls.last.request.headers["Idempotency-Key"] == k
    message.refresh_from_db()
    assert (message.status, message.error_code, message.wa_message_id) == ("sent", "", "wamid.LATE")


@respx.mock
def test_a_refused_or_sent_message_is_not_retried(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.recipient_blocked", "message": "Blocked."}})
    refused = delivered(lambda: send({"id": str(c.id), "text": "Hola"}))
    with pytest.raises(Conflict) as excinfo:
        run("whatsapp_inbox.message.retry", {"id": str(refused.id)})
    assert excinfo.value.code == "whatsapp_inbox.not_retryable"
    with pytest.raises(NotFound):
        run("whatsapp_inbox.message.retry", {"id": str(uuid.uuid7())})


@respx.mock
def test_an_early_status_is_matched_by_the_key_and_never_lost(delivered):
    c = ready()
    k = key()
    out = send({"id": str(c.id), "text": "Hola", "client_message_id": k})  # queued, not handed over yet
    early = system(
        "whatsapp_inbox.message.update_status",
        {"wa_message_id": "wamid.OUT", "client_message_id": k, "status": "delivered"},
    )
    assert early.model_dump() == {"updated": True, "status": "delivered"}
    message = stored(out)
    assert (message.status, message.wa_message_id) == ("delivered", "wamid.OUT")
    # erplora.com's 200 lands after it: the status never goes back to «Sent».
    answering()
    from apps.whatsapp_inbox import services

    services.deliver(A, out.id)
    message.refresh_from_db()
    assert (message.status, message.wa_message_id) == ("delivered", "wamid.OUT")


def test_a_conversation_is_named_by_its_number_or_the_customer_s_name():
    card("Ana López", "600111222")
    c = ready()
    assert send({"conversation": "600 111 222", "text": "Hola"}).conversation_id == c.id
    assert send({"conversation": "ana lópez", "text": "Hola"}).conversation_id == c.id
    with pytest.raises(NotFound) as excinfo:
        send({"conversation": "Marta", "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.conversation_not_found"


# ── WHATSAPP_INBOX-F33 Send a template ──────────────────────────────────────────────────────────


@respx.mock
def test_a_template_goes_out_of_the_window_rendered_with_its_variables(delivered):
    c = ready(sent_at=(NOW - dt.timedelta(days=3)).isoformat())
    route = answering()
    out = delivered(lambda: send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]}}))
    assert json.loads(route.calls.last.request.content)["template"] == {
        "name": "recordatorio",
        "language": "es",
        "variables": ["Ana", "viernes"],
    }
    assert (out.kind, out.template_name, out.body) == ("template", "recordatorio", "Hola Ana, te esperamos el viernes.")
    assert stored(out).template_variables == ["Ana", "viernes"]


def test_a_template_must_be_approved_and_fully_filled_in():
    c = ready()
    with pytest.raises(InvalidPayload) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana"]}})
    assert set(excinfo.value.fields) == {"template"}
    with pytest.raises(NotFound) as excinfo:
        send({"id": str(c.id), "template": {"name": "no_existe"}})
    assert excinfo.value.code == "whatsapp_inbox.template_not_found"
    connect(version=9, templates=[template("recordatorio", status="PAUSED")])
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]}})
    assert excinfo.value.code == "whatsapp_inbox.template_not_approved"


def test_a_template_in_two_languages_needs_the_language():
    c = ready()
    connect(version=9, templates=[template("recordatorio"), template("recordatorio", language="en")])
    with pytest.raises(InvalidPayload) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["a", "b"]}})
    assert set(excinfo.value.fields) == {"template"}
    out = send({"id": str(c.id), "template": {"name": "recordatorio", "language": "en", "variables": ["a", "b"]}})
    assert out.template_name == "recordatorio"


def test_marketing_needs_the_card_s_whatsapp_consent():
    c = ready()
    promo = {"id": str(c.id), "template": {"name": "promo"}}
    with pytest.raises(Conflict) as excinfo:
        send(promo)  # no card at all
    assert excinfo.value.code == "whatsapp_inbox.marketing_consent_missing"
    ana = card("Ana López", "600111222")
    run("whatsapp_inbox.conversation.link_customer", {"id": str(c.id), "customer_id": str(ana.id)})
    with pytest.raises(Conflict):
        send(promo)  # a card without consent
    run(
        "customer.consent.grant",
        {"customer_id": str(ana.id), "channel": "whatsapp", "notice_text": "¿Quieres recibir ofertas por WhatsApp?"},
    )
    assert send(promo).template_name == "promo"
    run("customer.consent.withdraw", {"customer_id": str(ana.id), "channel": "whatsapp"})
    with pytest.raises(Conflict):
        send(promo)


def test_a_template_to_a_number_that_never_wrote_opens_its_conversation():
    connect(templates=[template("recordatorio")])
    out = send({"to": "600 222 333", "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    c = Conversation.objects.get(phone="+34600222333")
    assert (out.conversation_id, c.status, c.unread_count, c.last_inbound_at) == (c.id, "open", 0, None)
    with pytest.raises(Conflict) as excinfo:
        send({"to": "600 444 555", "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.window_closed"
    assert not Conversation.objects.filter(phone="+34600444555").exists()


@pytest.mark.parametrize("typed", ["600222333", "600 222 333", "+34 600 222 333", "0034600222333"])
def test_a_number_typed_by_hand_goes_to_that_person_never_to_another_country(typed):
    """gh:whatsapp_inbox#279: a number written on a card or by voice is national unless it says its country."""
    connect(templates=[template("recordatorio")])
    send({"to": typed, "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    assert list(Conversation.objects.values_list("phone", flat=True)) == ["+34600222333"]


def test_an_incomplete_number_is_refused_and_nothing_is_kept():
    connect(templates=[template("recordatorio")])
    with pytest.raises(InvalidPayload) as excinfo:
        send({"to": "600 22", "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    assert "to" in excinfo.value.fields
    assert not Conversation.objects.exists() and not Message.objects.exists()


def test_marketing_to_a_number_without_conversation_reads_the_card_of_that_number():
    connect(templates=[template("promo", category="MARKETING", variables=0, body="¡Oferta!")])
    ana = card("Ana López", "600222333")
    run(
        "customer.consent.grant",
        {"customer_id": str(ana.id), "channel": "whatsapp", "notice_text": "¿Quieres recibir ofertas por WhatsApp?"},
    )
    out = send({"to": "+34 600 222 333", "template": {"name": "promo"}})
    assert Conversation.objects.get(pk=out.conversation_id).customer_id == ana.id
    with pytest.raises(Conflict) as excinfo:
        send({"to": "600 999 777", "template": {"name": "promo"}})  # nobody's card: no consent
    assert excinfo.value.code == "whatsapp_inbox.marketing_consent_missing"


# ── F05 read, F07 assign, F35 status ────────────────────────────────────────────────────────────


def test_opening_a_conversation_leaves_it_read_and_again_is_fine():
    receive("wamid.1")
    receive("wamid.2")
    c = conv()
    employee = ctx_for("hub_employee")
    assert (
        run(
            "whatsapp_inbox.conversation.mark_read", {"id": str(c.id)}, employee
        ).unread_count
        == 0
    )
    assert (
        run(
            "whatsapp_inbox.conversation.mark_read", {"id": str(c.id)}, employee
        ).unread_count
        == 0
    )
    assert len(events("whatsapp_inbox.conversation.read")) == 1


def test_an_employee_takes_a_conversation_but_assigns_nobody_else(make_user):
    receive("wamid.1")
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")
    out = run(
        "whatsapp_inbox.conversation.assign",
        {"id": str(conv().id), "assignee": "me"},
        ctx_for("hub_employee", actor=luis),
    )
    assert (out.assigned_to_id, out.assigned_to_name) == (luis.id, "Luis")
    with pytest.raises(PermissionDenied):
        run(
            "whatsapp_inbox.conversation.assign",
            {"id": str(conv().id), "assignee_id": marta.id},
            ctx_for("hub_employee", actor=luis),
        )
    assert events("whatsapp_inbox.conversation.assigned") == [
        {"id": str(conv().id), "assigned_to_id": luis.id}
    ]


def test_a_manager_assigns_by_name_and_unassigns(make_user):
    receive("wamid.1")
    boss = make_user("boss", role="hub_manager")
    make_user("marta", first_name="Marta", last_name="Ruiz", email="marta@example.com")
    manager = ctx_for("hub_manager", actor=boss)
    assert (
        run(
            "whatsapp_inbox.conversation.assign",
            {"conversation": "Ana", "assignee": "marta ruiz"},
            manager,
        ).assigned_to_name
        == "Marta Ruiz"
    )
    assert (
        run(
            "whatsapp_inbox.conversation.assign",
            {"conversation": "Ana", "assignee": "marta@example.com"},
            manager,
        ).assigned_to_name
        == "Marta Ruiz"
    )
    assert (
        run(
            "whatsapp_inbox.conversation.assign",
            {"conversation": "Ana", "unassign": True},
            manager,
        ).assigned_to_id
        is None
    )


def test_assign_to_me_never_takes_it_from_somebody_else(make_user):
    receive("wamid.1")
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")
    run(
        "whatsapp_inbox.conversation.assign",
        {"id": str(conv().id), "assignee": "me", "only_if_unassigned": True},
        ctx_for("hub_employee", actor=marta),
    )
    with pytest.raises(Conflict) as excinfo:
        run(
            "whatsapp_inbox.conversation.assign",
            {"id": str(conv().id), "assignee": "me", "only_if_unassigned": True},
            ctx_for("hub_employee", actor=luis),
        )
    assert excinfo.value.code == "whatsapp_inbox.already_assigned"
    assert excinfo.value.message == "This conversation is already with Marta."


def test_without_the_assign_permission_nobody_takes_it_from_somebody_else(make_user):
    receive("wamid.1")
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")
    run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), "assignee_id": marta.id}, ctx_for("hub_manager"))
    for payload in ({"assignee": "me"}, {"assignee": "me", "only_if_unassigned": False}, {"unassign": True}):
        with pytest.raises(Conflict) as excinfo:
            run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), **payload}, ctx_for("hub_employee", actor=luis))
        assert excinfo.value.code == "whatsapp_inbox.already_assigned"
        assert excinfo.value.message == "This conversation is already with Marta."
    assert conv().assigned_to_id == marta.id
    # A manager may take it over.
    taken = run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), "assignee_id": luis.id}, ctx_for("hub_manager"))
    assert taken.assigned_to_id == luis.id


def test_only_people_of_this_business_are_assigned(make_user):
    receive("wamid.1")
    stranger = make_user("pepe", host="b")
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "whatsapp_inbox.conversation.assign",
            {"id": str(conv().id), "assignee_id": stranger.id},
        )
    assert set(excinfo.value.fields) == {"assignee"}


def test_the_status_is_set_by_whoever_answers():
    receive("wamid.1")
    out = run(
        "whatsapp_inbox.conversation.set_status",
        {"id": str(conv().id), "status": "pending"},
        ctx_for("hub_employee"),
    )
    assert out.status == "pending"
    run(
        "whatsapp_inbox.conversation.set_status",
        {"id": str(conv().id), "status": "pending"},
    )
    run(
        "whatsapp_inbox.conversation.set_status",
        {"id": str(conv().id), "status": "closed"},
    )
    assert [
        e["status"] for e in events("whatsapp_inbox.conversation.status_changed")
    ] == ["pending", "closed"]


# ── WHATSAPP_INBOX-F37 Link a card ──────────────────────────────────────────────────────────────


def test_link_by_reference_create_and_unlink():
    receive("wamid.1", contact_name="Ana WhatsApp")
    c = conv()
    marta = card("Marta Ruiz", "699000111")
    assert (
        run(
            "whatsapp_inbox.conversation.link_customer",
            {"id": str(c.id), "customer": "Marta Ruiz"},
        ).customer_id
        == marta.id
    )
    assert (
        run(
            "whatsapp_inbox.conversation.link_customer",
            {"id": str(c.id), "unlink": True},
        ).customer_id
        is None
    )
    created = run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(c.id), "create": True},
        ctx_for("hub_employee"),
    )
    new = Customer.objects.get(pk=created.customer_id)
    assert (new.name, new.phone, new.source) == (
        "Ana WhatsApp",
        "+34600111222",
        "whatsapp",
    )
    assert created.customer_name == "Ana WhatsApp"


def test_creating_a_card_without_a_whatsapp_name_uses_the_number():
    receive("wamid.1", contact_name="")
    created = run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(conv().id), "create": True},
    )
    assert Customer.objects.get(pk=created.customer_id).name == "+34600111222"


# ── WHATSAPP_INBOX-F10 Erase a number's data ────────────────────────────────────────────────────


def test_erasing_a_number_blanks_every_personal_datum_and_frees_it(make_user):
    receive(
        "wamid.1",
        contact_name="Ana",
        media={
            "url": "https://erplora.com/m/1",
            "caption": "foto",
            "filename": "a.jpg",
        },
        payload={"from": "34600111222"},
    )
    c = conv()
    run("whatsapp_inbox.note.add", {"id": str(c.id), "text": "Alérgica al tinte"})
    out = run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    assert out.id == c.id
    c.refresh_from_db()
    assert (
        c.phone,
        c.contact_name,
        c.last_message_preview,
        c.status,
        c.unread_count,
        c.erased_at,
    ) == (
        "",
        "",
        "",
        "closed",
        0,
        NOW,
    )
    message = Message.objects.get()
    assert (
        message.body,
        message.media_url,
        message.media_caption,
        message.media_filename,
        message.payload,
    ) == (
        "",
        "",
        "",
        "",
        {},
    )
    assert (
        message.wa_message_id == "wamid.1"
    )  # kept: a redelivery is never stored again
    assert Note.objects.count() == 0
    assert events("whatsapp_inbox.conversation.erased") == [{"id": str(c.id)}]
    # Twice is harmless.
    run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    assert Conversation.objects.get(pk=c.id).erased_at == NOW
    # A redelivery of an erased message stays erased.
    assert receive("wamid.1").created is False
    assert Conversation.objects.filter(erased_at__isnull=True).count() == 0


ERASE = f"{SAAS}/internal/whatsapp/erase"


@respx.mock
def test_no_notice_of_the_app_keeps_her_number_her_name_or_what_was_said(delivered):
    """gh:hub#2474, #2467, #2477: the internal history keeps the notices for days after an erasure; they
    carry identifiers only, so erasing the conversation leaves nothing of her there."""
    c = ready(contact_name="Ana Secreta", text="Mi alergia es al tinte")
    answering()
    delivered(lambda: send({"id": str(c.id), "text": "Apuntado, Ana"}))
    run("whatsapp_inbox.note.add", {"id": str(c.id), "text": "Nota sobre Ana"})
    run("whatsapp_inbox.conversation.set_status", {"id": str(c.id), "status": "pending"})
    respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    notices = [json.dumps(e.payload, ensure_ascii=False) for e in OutboxEvent.objects.filter(name__startswith="whatsapp_inbox.")]
    assert len(notices) >= 5
    for said in ("600111222", "Ana Secreta", "alergia", "Apuntado", "Nota sobre"):
        assert not [notice for notice in notices if said in notice], said


@respx.mock
def test_erasing_asks_erplora_to_forget_the_number_after_the_commit(django_capture_on_commit_callbacks):
    receive("wamid.1")
    receive("wamid.2")
    c = conv()
    route = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    with django_capture_on_commit_callbacks(execute=True):
        run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
        assert route.call_count == 0
        c.refresh_from_db()
        assert (c.phone, c.erase_status, c.erase_phone) == ("", "pending", "+34600111222")
    assert json.loads(route.calls.last.request.content) == {
        "hub": "a",
        "phone": "+34600111222",
        "wa_message_ids": ["wamid.1", "wamid.2"],
    }
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone) == ("done", "")


@respx.mock
def test_an_erasure_erplora_does_not_confirm_stays_pending_and_is_asked_again(delivered):
    receive("wamid.1")
    c = conv()
    route = respx.post(ERASE).mock(side_effect=[httpx.ConnectError("refused")])
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone, c.phone) == ("pending", "+34600111222", "")
    route.side_effect = [httpx.Response(200, json={"erased": True})]
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone) == ("done", "")


@respx.mock
def test_the_worker_resumes_what_was_left_for_erplora(delivered, fixed_clock, monkeypatch):
    c = ready()
    stuck = send({"id": str(c.id), "text": "Hola"})  # queued; its COMMIT's delivery never ran
    receive("wamid.X", "34600999888")
    other = Conversation.objects.get(phone="+34600999888")
    run("whatsapp_inbox.conversation.erase", {"id": str(other.id)})  # pending at erplora.com
    answering()
    respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    # Not before 2 minutes: a delivery may still be on its way.
    early = delivered(lambda: system("whatsapp_inbox.delivery.resume"))
    assert early.model_dump() == {"messages": 0, "erasures": 0, "templates": 0, "template_deletions": 0}
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    out = delivered(lambda: system("whatsapp_inbox.delivery.resume"))
    assert out.model_dump() == {"messages": 1, "erasures": 1, "templates": 0, "template_deletions": 0}
    assert stored(stuck).status == "sent"
    other.refresh_from_db()
    assert other.erase_status == "done"


def test_only_owner_and_admin_erase():
    receive("wamid.1")
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            run(
                "whatsapp_inbox.conversation.erase",
                {"id": str(conv().id)},
                ctx_for(role),
            )


# ── WHATSAPP_INBOX-F36 Internal notes ───────────────────────────────────────────────────────────


def test_a_note_keeps_its_author_and_only_they_or_a_manager_delete_it(make_user):
    receive("wamid.1")
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")
    note = run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": " Llamar mañana "},
        ctx_for("hub_employee", actor=luis),
    )
    assert (note.text, note.author_id, note.author_name, note.created_at) == (
        "Llamar mañana",
        luis.id,
        "Luis",
        NOW,
    )
    with pytest.raises(PermissionDenied):
        run(
            "whatsapp_inbox.note.delete",
            {"id": str(note.id)},
            ctx_for("hub_employee", actor=marta),
        )
    assert (
        run(
            "whatsapp_inbox.note.delete",
            {"id": str(note.id)},
            ctx_for("hub_employee", actor=luis),
        ).id
        == note.id
    )
    again = run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": "Otra"},
        ctx_for("hub_employee", actor=luis),
    )
    run("whatsapp_inbox.note.delete", {"id": str(again.id)}, ctx_for("hub_manager"))
    assert Note.objects.count() == 0
    with pytest.raises(NotFound):
        run("whatsapp_inbox.note.delete", {"id": str(again.id)})
    assert len(events("whatsapp_inbox.note.added")) == 2
    assert len(events("whatsapp_inbox.note.deleted")) == 2


def test_an_erased_conversation_is_not_found_by_the_inbox():
    receive("wamid.1")
    c = conv()
    run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    for name, payload in (
        ("whatsapp_inbox.conversation.mark_read", {"id": str(c.id)}),
        ("whatsapp_inbox.note.add", {"id": str(c.id), "text": "x"}),
        ("whatsapp_inbox.conversation.set_status", {"id": str(c.id), "status": "open"}),
    ):
        with pytest.raises(NotFound):
            run(name, payload)
