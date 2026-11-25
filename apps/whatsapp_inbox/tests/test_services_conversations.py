"""Working a conversation (WHATSAPP_INBOX-F05, F07, F35, F37): reading it, assigning it, its status and the card it
is linked to, against the real Customers app.
"""

import pytest
from live.errors import Conflict, InvalidPayload, PermissionDenied

from apps.customer.models import Customer
from apps.whatsapp_inbox.tests.conftest import B, HUB_DB, card, conv, ctx_for, events, receive, run

pytestmark = HUB_DB


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
    assert (out.assigned_to_id, out.assigned_to_name) == (luis.person.id, "Luis")
    with pytest.raises(PermissionDenied):
        run(
            "whatsapp_inbox.conversation.assign",
            {"id": str(conv().id), "assignee_id": str(marta.person.id)},
            ctx_for("hub_employee", actor=luis),
        )
    assert events("whatsapp_inbox.conversation.assigned") == [
        {"id": str(conv().id), "assigned_to_id": str(luis.person.id)}
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


def test_a_manager_assigns_by_first_name_or_username_and_two_of_a_name_are_asked_apart(make_user):
    # The people of the business's database (base.HubUser): their full name, its first word, the username or the email.
    receive("wamid.1")
    manager = ctx_for("hub_manager", actor=make_user("boss", role="hub_manager"))
    make_user("marta", first_name="Marta", last_name="Ruiz")

    def assign(reference):
        return run("whatsapp_inbox.conversation.assign", {"conversation": "Ana", "assignee": reference}, manager)

    assert assign("MARTA").assigned_to_name == "Marta Ruiz"
    assert assign("marta").assigned_to_name == "Marta Ruiz"
    make_user("marta.gil", first_name="Marta", last_name="Gil")
    with pytest.raises(InvalidPayload) as several:
        assign("Marta")
    assert set(several.value.fields) == {"assignee"}
    with pytest.raises(InvalidPayload) as nobody:
        assign("Mar")
    assert set(nobody.value.fields) == {"assignee"}


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
    run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), "assignee_id": str(marta.person.id)}, ctx_for("hub_manager"))
    for payload in ({"assignee": "me"}, {"assignee": "me", "only_if_unassigned": False}, {"unassign": True}):
        with pytest.raises(Conflict) as excinfo:
            run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), **payload}, ctx_for("hub_employee", actor=luis))
        assert excinfo.value.code == "whatsapp_inbox.already_assigned"
        assert excinfo.value.message == "This conversation is already with Marta."
    assert conv().assigned_to_id == marta.person.id
    # A manager may take it over.
    taken = run("whatsapp_inbox.conversation.assign", {"id": str(conv().id), "assignee_id": str(luis.person.id)}, ctx_for("hub_manager"))
    assert taken.assigned_to_id == luis.person.id


def test_only_people_of_this_business_are_assigned(make_user):
    receive("wamid.1")
    stranger = make_user("pepe", host=B.key)
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "whatsapp_inbox.conversation.assign",
            {"id": str(conv().id), "assignee_id": str(stranger.person.id)},
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
