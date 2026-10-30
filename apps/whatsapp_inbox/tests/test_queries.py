"""Read operations of the WhatsApp inbox: the inbox list, a conversation, its thread and notes, the
exact-number lookup for other apps, the summary, the templates, the channel and the team."""

import datetime as dt

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.tests.conftest import (
    NOW,
    card,
    connect,
    ctx_for,
    receive,
    run,
    template,
)

pytestmark = pytest.mark.django_db


def listed(params=None, ctx=None) -> list[str]:
    return [
        row.phone
        for row in run("whatsapp_inbox.conversation.list", params or {}, ctx).rows
    ]


def at(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()


@pytest.fixture
def three():
    """Three conversations: Ana (newest), Bea and Carla (oldest)."""
    receive("wamid.c", "34600333333", contact_name="Carla", sent_at=at(30))
    receive("wamid.b", "34600222222", contact_name="Bea", sent_at=at(20))
    receive("wamid.a", "34600111111", contact_name="Ana", sent_at=at(10))
    return {c.contact_name: c for c in Conversation.objects.all()}


# ── The inbox list (F05, F09) ───────────────────────────────────────────────────────────────────


def test_the_inbox_shows_the_latest_activity_first(three):
    page = run("whatsapp_inbox.conversation.list", {}, ctx_for("hub_employee"))
    assert [row.contact_name for row in page.rows] == ["Ana", "Bea", "Carla"]
    assert (page.total, page.limit, page.offset) == (3, 50, 0)
    assert page.rows[0].display_name == "Ana"
    assert (
        run("whatsapp_inbox.conversation.list", {"limit": 1, "offset": 1})
        .rows[0]
        .contact_name
        == "Bea"
    )


@pytest.mark.parametrize(
    "search",
    [
        "600 111 111",
        "+34 600 111 111",
        "0034 600-111-111",
        "(600) 111.111",
        "600 111",
        "Ana",
        "ana",
    ],
)
def test_a_number_written_any_way_or_a_name_finds_the_conversation(three, search):
    assert listed({"search": search}) == ["+34600111111"]


def test_the_card_s_name_is_searched_and_shown(three):
    ana = card("Ana López", "600111111")
    run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(three["Ana"].id), "customer_id": str(ana.id)},
    )
    assert listed({"search": "lópez"}) == ["+34600111111"]
    row = run("whatsapp_inbox.conversation.list", {"search": "lópez"}).rows[0]
    assert (row.display_name, row.customer_name, row.customer_id) == (
        "Ana López",
        "Ana López",
        ana.id,
    )
    assert listed({"customer_id": str(ana.id)}) == ["+34600111111"]


def test_filters_by_status_unread_and_assignment(three, make_user):
    luis = make_user("luis")
    run(
        "whatsapp_inbox.conversation.set_status",
        {"id": str(three["Bea"].id), "status": "pending"},
    )
    run("whatsapp_inbox.conversation.mark_read", {"id": str(three["Carla"].id)})
    run(
        "whatsapp_inbox.conversation.assign",
        {"id": str(three["Ana"].id), "assignee_id": str(luis.person.id)},
    )
    assert listed({"status": "pending"}) == ["+34600222222"]
    assert listed({"unread": True}) == ["+34600111111", "+34600222222"]
    assert listed({"unread": False}) == ["+34600333333"]
    assert listed({"assigned": "me"}, ctx_for("hub_employee", actor=luis)) == [
        "+34600111111"
    ]
    assert listed({"assigned": str(luis.person.id)}) == ["+34600111111"]
    assert listed({"assigned": "none"}) == ["+34600222222", "+34600333333"]


def test_sorting_by_any_column_keeps_a_stable_order(three):
    assert listed({"sort": "contact", "dir": "asc"}) == [
        "+34600111111",
        "+34600222222",
        "+34600333333",
    ]
    assert listed({"sort": "phone", "dir": "desc"}) == [
        "+34600333333",
        "+34600222222",
        "+34600111111",
    ]
    assert len(listed({"sort": "unread_count"})) == 3
    assert len(listed({"sort": "status"})) == 3
    assert len(listed({"sort": "assigned_to"})) == 3


def test_an_empty_value_goes_last_whichever_way_it_is_sorted(three, make_user):
    """gh:hub#2099: sorting by a column some rows leave empty never puts the empty ones first."""
    luis = make_user("luis")
    run("whatsapp_inbox.conversation.assign", {"id": str(three["Bea"].id), "assignee_id": str(luis.person.id)})
    assert listed({"sort": "assigned_to", "dir": "desc"})[0] == "+34600222222"
    assert listed({"sort": "assigned_to", "dir": "asc"})[0] == "+34600222222"


def test_erased_conversations_leave_the_inbox(three):
    run("whatsapp_inbox.conversation.erase", {"id": str(three["Bea"].id)})
    assert listed() == ["+34600111111", "+34600333333"]


# ── A conversation (F05, F32) ───────────────────────────────────────────────────────────────────


def test_the_detail_says_whether_the_window_is_open_and_whether_it_can_send(three):
    detail = run("whatsapp_inbox.conversation.detail", {"id": str(three["Ana"].id)})
    assert (detail.window_open, detail.window_expires_at) == (
        True,
        NOW - dt.timedelta(minutes=10) + dt.timedelta(hours=24),
    )
    assert (detail.can_send, detail.send_blocked) == (False, "not_connected")
    connect(version=1)
    assert (
        run("whatsapp_inbox.conversation.detail", {"conversation": "Ana"}).can_send
        is True
    )
    connect(version=2, monthly_limit=10, monthly_usage=10, usage_month="2026-10")
    assert (
        run("whatsapp_inbox.conversation.detail", {"conversation": "Ana"}).send_blocked
        == "cap_reached"
    )


def test_the_detail_says_when_there_is_no_saas_to_send_through(three, settings):
    connect(version=1)
    settings.SAAS_INTERNAL_URL = ""
    assert (
        run("whatsapp_inbox.conversation.detail", {"conversation": "Ana"}).send_blocked
        == "unconfigured"
    )


def test_after_24_hours_the_window_is_closed(three, fixed_clock, monkeypatch):
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(hours=24))
    assert (
        run("whatsapp_inbox.conversation.detail", {"conversation": "Ana"}).window_open
        is False
    )


def test_a_reference_that_fits_several_or_none(three):
    receive("wamid.x", "34600999999", contact_name="Ana")
    with pytest.raises(Conflict) as excinfo:
        run("whatsapp_inbox.conversation.detail", {"conversation": "Ana"})
    assert excinfo.value.code == "whatsapp_inbox.conversation_ambiguous"
    with pytest.raises(NotFound) as excinfo:
        run("whatsapp_inbox.conversation.detail", {"conversation": "Zoe"})
    assert excinfo.value.code == "whatsapp_inbox.conversation_not_found"
    assert (
        run(
            "whatsapp_inbox.conversation.detail", {"conversation": "+34 600 999 999"}
        ).phone
        == "+34600999999"
    )


def test_by_phone_answers_only_the_exact_international_number(three):
    hit = run("whatsapp_inbox.conversation.by_phone", {"phone": "+34600111111"})
    assert hit.model_dump() == {
        "phone_is_international": True,
        "phone": "+34600111111",
        "conversation_id": three["Ana"].id,
    }
    assert (
        run(
            "whatsapp_inbox.conversation.by_phone", {"phone": "+34600000000"}
        ).conversation_id
        is None
    )
    # Not international: never matched against anybody's conversation.
    loose = run("whatsapp_inbox.conversation.by_phone", {"phone": "600111111"})
    assert loose.model_dump() == {
        "phone_is_international": False,
        "phone": "",
        "conversation_id": None,
    }
    assert (
        run(
            "whatsapp_inbox.conversation.by_phone", {"phone": "+34 600 111"}
        ).phone_is_international
        is False
    )


def test_the_summary_counts_who_waits(three):
    run("whatsapp_inbox.conversation.mark_read", {"id": str(three["Carla"].id)})
    run(
        "whatsapp_inbox.conversation.set_status",
        {"id": str(three["Bea"].id), "status": "closed"},
    )
    summary = run("whatsapp_inbox.conversation.summary", {}, ctx_for("hub_employee"))
    # Carla is read but her message still has no answer; Bea is closed.
    assert summary.model_dump() == {
        "open": 2,
        "unread_conversations": 2,
        "awaiting_reply": 2,
        "cap_reached": False,
    }


# ── The thread and the notes ────────────────────────────────────────────────────────────────────


def test_the_thread_comes_newest_first_in_pages(three):
    receive("wamid.a2", "34600111111", text="¿Y el jueves?", sent_at=at(5))
    page = run(
        "whatsapp_inbox.message.list",
        {"id": str(three["Ana"].id)},
        ctx_for("hub_employee"),
    )
    assert [m.body for m in page.rows] == [
        "¿Y el jueves?",
        "Hola, ¿tenéis hora mañana?",
    ]
    assert page.total == 2
    assert (
        run(
            "whatsapp_inbox.message.list",
            {"conversation": "Ana", "limit": 1, "offset": 1},
        )
        .rows[0]
        .wa_message_id
        == "wamid.a"
    )


def test_notes_say_who_may_delete_them(three, make_user):
    luis = make_user("luis", first_name="Luis")
    run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": "Mía"},
        ctx_for("hub_employee", actor=luis),
    )
    run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": "Del jefe"},
        ctx_for("hub_manager"),
    )
    rows = run(
        "whatsapp_inbox.note.list",
        {"conversation": "Ana"},
        ctx_for("hub_employee", actor=luis),
    ).rows
    assert {(note.text, note.can_delete) for note in rows} == {
        ("Mía", True),
        ("Del jefe", False),
    }
    rows = run(
        "whatsapp_inbox.note.list", {"conversation": "Ana"}, ctx_for("hub_manager")
    ).rows
    assert all(note.can_delete for note in rows)


# ── Templates, channel and team ─────────────────────────────────────────────────────────────────


def test_templates_list_by_name_and_filter_by_state():
    connect(
        templates=[
            template("recordatorio"),
            template("promo_otono", category="MARKETING"),
            template("vieja", status="REJECTED", rejected_reason="INVALID_FORMAT"),
        ]
    )
    page = run("whatsapp_inbox.template.list", {}, ctx_for("hub_employee"))
    assert [t.name for t in page.rows] == ["promo_otono", "recordatorio", "vieja"]
    assert [
        t.name for t in run("whatsapp_inbox.template.list", {"status": "APPROVED"}).rows
    ] == ["promo_otono", "recordatorio"]
    assert [
        t.name for t in run("whatsapp_inbox.template.list", {"search": "record"}).rows
    ] == ["recordatorio"]
    assert [
        t.name
        for t in run("whatsapp_inbox.template.list", {"category": "MARKETING"}).rows
    ] == ["promo_otono"]


def test_the_channel_before_erplora_speaks_and_after():
    empty = run("whatsapp_inbox.channel.get", {}, ctx_for("hub_employee"))
    assert (empty.status, empty.monthly_limit, empty.cap_reached, empty.synced_at) == (
        "not_connected",
        0,
        False,
        None,
    )
    assert empty.manage_url
    connect(version=1, monthly_limit=150, monthly_usage=150, usage_month="2026-09")
    september = run("whatsapp_inbox.channel.get", {})
    # Last month's figure is nothing spent this month.
    assert (september.monthly_usage, september.cap_reached) == (0, False)
    connect(version=2, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    assert run("whatsapp_inbox.channel.get", {}).cap_reached is True


def test_the_team_is_the_people_of_this_business(make_user):
    make_user("luis", first_name="Luis", last_name="Gil")
    make_user("marta", first_name="Marta", role="hub_manager")
    make_user("pepe", host="b")
    page = run("whatsapp_inbox.agent.list", {}, ctx_for("hub_employee"))
    assert [(a.name, a.role) for a in page.rows] == [
        ("Luis Gil", "hub_employee"),
        ("Marta", "hub_manager"),
    ]
    assert [
        a.name for a in run("whatsapp_inbox.agent.list", {"search": "gil"}).rows
    ] == ["Luis Gil"]


def test_settings_reads_are_whoever_may_read_the_inbox():
    for name in (
        "whatsapp_inbox.conversation.list",
        "whatsapp_inbox.channel.get",
        "whatsapp_inbox.conversation.summary",
    ):
        run(name, {}, ctx_for("hub_employee"))
    with pytest.raises(PermissionDenied):
        run("whatsapp_inbox.conversation.list", {}, ctx_for("nobody"))


def test_a_reference_by_voice_ignores_accents_case_emoji_and_extra_spaces(three):
    ana = card("Ana López", "600111111")
    run("whatsapp_inbox.conversation.link_customer", {"id": str(three["Ana"].id), "customer_id": str(ana.id)})
    receive("wamid.z", "34600555555", contact_name="Zoé 🌸")
    assert run("whatsapp_inbox.conversation.detail", {"conversation": "ana lopez"}).id == three["Ana"].id
    assert run("whatsapp_inbox.conversation.detail", {"conversation": "  ANA   López "}).id == three["Ana"].id
    assert run("whatsapp_inbox.conversation.detail", {"conversation": "zoe"}).phone == "+34600555555"
    # Exactly one: the card's name and another profile with the same name are two.
    receive("wamid.y", "34600666666", contact_name="Ana Lopez")
    with pytest.raises(Conflict):
        run("whatsapp_inbox.conversation.detail", {"conversation": "ana lopez"})


# ── Who waits for an answer: the bell's count and the device's notices (WHATSAPP_INBOX-F09) ─────────────────


def answer(conversation: Conversation, text: str = "¡Hola! Sí, a las 17:00.") -> None:
    """The team answers ``conversation`` from the Hub (its delivery to erplora.com is left for after the COMMIT)."""
    run(
        "whatsapp_inbox.message.send",
        {"id": str(conversation.id), "text": text, "client_message_id": "0199e000-0000-7000-8000-0000000000f1"},
    )


def echo(phone: str, wa_id: str = "wamid.echo", minutes_ago: int = 1) -> None:
    """The business answers from its own phone: erplora.com hands the Hub the echo of that message."""
    receive(wa_id, phone, direction="outbound", text="Te llamo ahora", contact_name="", sent_at=at(minutes_ago))


def waiting_count(ctx=None) -> dict:
    return run("whatsapp_inbox.conversation.count_awaiting_reply", {}, ctx).model_dump()


def test_the_count_is_the_open_conversations_whose_last_message_is_the_customers(three):
    connect()
    answer(three["Ana"])
    echo("34600222222")
    receive("wamid.d", "34600444444", contact_name="Dora", sent_at=at(8))
    run("whatsapp_inbox.conversation.set_status", {"id": str(three["Carla"].id), "status": "pending"})
    receive("wamid.e", "34600555555", contact_name="Eva", sent_at=at(7))
    run("whatsapp_inbox.conversation.set_status", {"id": str(Conversation.objects.get(contact_name="Eva").id), "status": "closed"})
    receive("wamid.f", "34600666666", contact_name="Fina", sent_at=at(6))
    run("whatsapp_inbox.conversation.erase", {"id": str(Conversation.objects.get(contact_name="Fina").id)})

    # Answered from the Hub (Ana) or from the phone (Bea), pending (Carla), closed (Eva) or erased (Fina): only Dora waits.
    assert waiting_count(ctx_for("hub_employee")) == {"count": 1}


def test_with_nobody_waiting_the_count_is_one_row_of_zero():
    assert waiting_count() == {"count": 0}


def test_the_count_is_the_summarys_waiting_for_an_answer(three):
    run("whatsapp_inbox.conversation.set_status", {"id": str(three["Bea"].id), "status": "closed"})
    run("whatsapp_inbox.conversation.mark_read", {"id": str(three["Carla"].id)})
    echo("34600333333")
    summary = run("whatsapp_inbox.conversation.summary", {})
    # Carla, read and answered from the phone, is open but waits no more: open and waiting are not the same count.
    assert (summary.open, summary.awaiting_reply) == (2, 1)
    assert waiting_count()["count"] == summary.awaiting_reply


def test_a_customer_writing_again_counts_her_again(three):
    connect()
    answer(three["Ana"])
    run("whatsapp_inbox.conversation.set_status", {"id": str(three["Bea"].id), "status": "closed"})
    assert waiting_count() == {"count": 1}
    # After the answer (sent at NOW, the fixed clock): Ana writes again, and Bea, closed, opens it again by writing.
    later = (NOW + dt.timedelta(minutes=1)).isoformat()
    receive("wamid.a2", "34600111111", contact_name="Ana", text="¿Y el jueves?", sent_at=later)
    receive("wamid.b2", "34600222222", contact_name="Bea", text="Otra cosa", sent_at=later)
    assert waiting_count() == {"count": 3}


def notices(params=None, ctx=None) -> list[dict]:
    return run("whatsapp_inbox.conversation.notices", params or {}, ctx).model_dump(mode="json")["rows"]


def test_the_notices_are_the_customers_left_waiting_the_newest_first(three):
    lopez = card("Ana López", "600111111")
    run("whatsapp_inbox.conversation.link_customer", {"id": str(three["Ana"].id), "customer_id": str(lopez.id)})
    receive("wamid.c2", "34600333333", contact_name="Carla", text="¿Me confirmas?", sent_at=at(2))

    rows = notices(ctx=ctx_for("hub_employee"))

    assert [(row["id"], row["display_name"], row["last_message_preview"]) for row in rows] == [
        (str(three["Carla"].id), "Carla", "¿Me confirmas?"),
        (str(three["Ana"].id), "Ana López", "Hola, ¿tenéis hora mañana?"),
        (str(three["Bea"].id), "Bea", "Hola, ¿tenéis hora mañana?"),
    ]
    # Each one is the customer's last message: a new one is told again.
    assert [row["at"] for row in rows] == [
        (NOW - dt.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z") for minutes in (2, 10, 20)
    ]


def test_an_answered_pending_closed_erased_or_old_conversation_is_not_told(three):
    connect()
    answer(three["Ana"])
    run("whatsapp_inbox.conversation.set_status", {"id": str(three["Bea"].id), "status": "pending"})
    run("whatsapp_inbox.conversation.erase", {"id": str(three["Carla"].id)})
    receive("wamid.d", "34600444444", contact_name="Dora", sent_at=at(25 * 60))
    receive("wamid.e", "34600555555", contact_name="", sent_at=at(3))

    # Dora wrote 25 hours ago (beyond the last day); a customer with no WhatsApp name is told by her number.
    assert [row["display_name"] for row in notices()] == ["+34600555555"]
    assert [row["display_name"] for row in notices({"since": at(26 * 60)})] == ["+34600555555", "Dora"]
    assert len(notices({"since": at(26 * 60), "limit": 1})) == 1


def test_the_notices_are_whoever_may_read_the_inbox(three):
    with pytest.raises(PermissionDenied):
        notices(ctx=ctx_for("nobody"))
    with pytest.raises(PermissionDenied):
        waiting_count(ctx_for("nobody"))
