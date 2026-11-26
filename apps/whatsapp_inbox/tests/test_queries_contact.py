"""A customer's WhatsApp number reaches only whoever sees the customers' contact details (``base.view_customer_contact``).
Anyone else still works the inbox (reads and answers the conversations) by the customer's name, without the number, on
every door (the API, the assistant, the live list), and cannot find, filter or sort the conversations by it. A
conversation with no name is called by its number masked as the shared inboxes do: its first three and last four
digits («+346••••2333»).

No basic role lacks the permission today: these tests take the employee's and the manager's roles without it, as a role
the business makes may be. Every caller is a person signed in to business A, never a made-up actor."""

import json

import httpx
import pytest
import respx
from django.apps import apps
from django.test import RequestFactory
from live.assistant.running import run_tool
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.whatsapp_inbox.models.conversations import Conversation, Message
from base.operations import HubContextBuilder
from base.sensitive import VIEW_CUSTOMER_CONTACT
from base.tenancy.context import current_alias

from .conftest import HOST, HUB_DB, A, card, connect, receive

pytestmark = HUB_DB

ANA = "+34600111222"
NAMELESS = "+34611222333"
MASKED = "+346••••2333"
SEERS = ["hub_owner", "hub_manager", "hub_employee"]
LIST = "/whatsapp_inbox/conversations"
DETAIL = "/whatsapp_inbox/conversations/detail"


@pytest.fixture
def chats(db):
    """Ana, by her WhatsApp name, and somebody who wrote without one."""
    receive("wamid.1", phone=ANA[1:], contact_name="Ana")
    receive("wamid.2", phone=NAMELESS[1:], contact_name="")
    return {row.phone: row for row in Conversation.objects.all()}


@pytest.fixture
def lacking(monkeypatch):
    """The employee's and the manager's roles without «View customer contact details»."""
    roles = apps.get_app_config("base").role_permissions
    for role in ("hub_employee", "hub_manager"):
        monkeypatch.setitem(roles, role, [name for name in roles[role] if name != VIEW_CUSTOMER_CONTACT])


@pytest.fixture
def as_role(client, make_user):
    def sign_in(role: str):
        user = make_user(role, host=A.key, role=role)
        client.force_login(user)
        return user

    return sign_in


def told(rows: list[dict]) -> set[tuple]:
    return {(row["display_name"], row["phone"]) for row in rows}


def context_of(user):
    """The context a request of ``user`` to business A gets, as every door builds it."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


def without_contact(monkeypatch) -> None:
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])


# ── What comes out ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", SEERS)
def test_whoever_sees_the_contact_gets_the_number(chats, as_role, client, role):
    as_role(role)
    assert told(get(client, LIST).json()["rows"]) == {("Ana", ANA), (NAMELESS, NAMELESS)}
    detail = get(client, DETAIL, id=str(chats[NAMELESS].id)).json()
    assert (detail["display_name"], detail["phone"]) == (NAMELESS, NAMELESS)
    message = Message.objects.get(conversation=chats[NAMELESS])
    read = get(client, "/whatsapp_inbox/messages/detail", id=str(message.id)).json()
    assert (read["display_name"], read["phone"]) == (NAMELESS, NAMELESS)


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_without_it_the_inbox_names_them_without_the_number(chats, lacking, as_role, client, role):
    as_role(role)
    assert told(get(client, LIST).json()["rows"]) == {("Ana", None), (MASKED, None)}
    detail = get(client, DETAIL, id=str(chats[NAMELESS].id)).json()
    assert (detail["display_name"], detail["phone"]) == (MASKED, None)
    message = Message.objects.get(conversation=chats[NAMELESS])
    read = get(client, "/whatsapp_inbox/messages/detail", id=str(message.id)).json()
    assert (read["display_name"], read["phone"]) == (MASKED, None)
    notices = get(client, "/whatsapp_inbox/conversations/notices").json()["rows"]
    assert {row["display_name"] for row in notices} == {"Ana", MASKED}


@respx.mock
def test_without_it_the_inbox_is_still_read_and_answered(chats, lacking, as_role, client, django_capture_on_commit_callbacks):
    connect()
    respx.post("http://saas.test/internal/whatsapp/send").mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    as_role("hub_employee")
    conversation = str(chats[ANA].id)
    thread = get(client, "/whatsapp_inbox/messages", id=conversation).json()["rows"]
    assert [row["body"] for row in thread] == ["Hola, ¿tenéis hora mañana?"]
    assert post(client, "/whatsapp_inbox/conversations/mark_read", {"id": conversation}).json()["unread_count"] == 0
    key = "0199e000-0000-7000-8000-0000000000c1"
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
        sent = post(client, "/whatsapp_inbox/messages/send", {"id": conversation, "text": "¡Sí, a las 10!", "client_message_id": key})
    assert (sent.status_code, Message.objects.get(pk=sent.json()["id"]).status) == (201, "sent")


def test_the_assistant_gives_the_conversation_without_the_number_to_whoever_lacks_it(chats, make_user, monkeypatch):
    employee = make_user("eva", host=A.key, role="hub_employee")

    def answer() -> tuple:
        args = json.dumps({"id": str(chats[NAMELESS].id)})
        outcome = run_tool(context_of(employee), operation("whatsapp_inbox.conversation.detail"), args)
        assert outcome.outcome == "ok", outcome.content
        detail = json.loads(outcome.content)
        return detail["display_name"], detail["phone"]

    assert answer() == (NAMELESS, NAMELESS)
    without_contact(monkeypatch)
    assert answer() == (MASKED, None)


def test_the_live_list_answers_without_the_number_to_whoever_lacks_it(chats, make_user, monkeypatch):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    employee = make_user("eva", host=A.key, role="hub_employee")
    op = operation("whatsapp_inbox.conversation.list")

    def rows() -> set[tuple]:
        sub = Subscription(id="inbox", op=op, params=op.input.model_validate({}))
        frame = executor._run_one(Stream(context_of(employee)), sub).decode()
        return told(json.loads(frame.split("data: ", 1)[1])["data"]["rows"])

    assert rows() == {("Ana", ANA), (NAMELESS, NAMELESS)}
    without_contact(monkeypatch)
    assert rows() == {("Ana", None), (MASKED, None)}


# ── Finding and sorting by it ─────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("said", ["600 111", "0034600111222", "+34 600 111 222"])
def test_the_search_looks_into_the_number_only_for_whoever_sees_it(chats, lacking, as_role, client, said):
    as_role("hub_owner")
    assert told(get(client, LIST, search=said).json()["rows"]) == {("Ana", ANA)}
    as_role("hub_employee")
    assert get(client, LIST, search=said).json()["rows"] == []
    assert told(get(client, LIST, search="Ana").json()["rows"]) == {("Ana", None)}


@pytest.mark.parametrize("said", ["ana@example", "600 111"])
def test_the_search_looks_into_the_joined_card_s_contact_only_for_whoever_sees_it(lacking, as_role, client, said):
    # The conversation is joined to her card by her number (WHATSAPP_INBOX-F04); the card has her email and phone.
    card("Ana López", phone="600111222", email="ana@example.com")
    receive("wamid.1", phone=ANA[1:], contact_name="")
    as_role("hub_owner")
    assert told(get(client, LIST, search=said).json()["rows"]) == {("Ana López", ANA)}
    as_role("hub_employee")
    assert get(client, LIST, search=said).json()["rows"] == []
    assert told(get(client, LIST, search="lópez").json()["rows"]) == {("Ana López", None)}


def test_a_conversation_named_by_its_number_is_found_only_by_whoever_sees_it(chats, lacking, as_role, client):
    as_role("hub_owner")
    assert get(client, DETAIL, conversation="600 111 222").json()["id"] == str(chats[ANA].id)
    as_role("hub_employee")
    missed = get(client, DETAIL, conversation="600 111 222")
    assert (missed.status_code, missed.json()["error"]["code"]) == (404, "whatsapp_inbox.conversation_not_found")
    assert get(client, DETAIL, conversation="Ana").json()["id"] == str(chats[ANA].id)


def test_a_step_on_a_conversation_named_by_its_number_is_refused_without_it(chats, lacking, as_role, client):
    as_role("hub_employee")
    payload = {"conversation": "+34 600 111 222", "status": "pending"}
    missed = post(client, "/whatsapp_inbox/conversations/set_status", payload)
    assert (missed.status_code, missed.json()["error"]["code"]) == (404, "whatsapp_inbox.conversation_not_found")
    assert Conversation.objects.get(pk=chats[ANA].pk).status == "open"
    as_role("hub_owner")
    assert post(client, "/whatsapp_inbox/conversations/set_status", payload).json()["status"] == "pending"


def test_asking_whose_conversation_a_number_is_is_refused_without_it(chats, lacking, as_role, client):
    as_role("hub_employee")
    refused = get(client, "/whatsapp_inbox/conversations/by_phone", phone=ANA)
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    as_role("hub_owner")
    found = get(client, "/whatsapp_inbox/conversations/by_phone", phone=ANA).json()
    assert (found["phone"], found["conversation_id"]) == (ANA, str(chats[ANA].id))


@respx.mock
def test_writing_to_a_typed_number_is_refused_without_it(chats, lacking, as_role, client, django_capture_on_commit_callbacks):
    # A number typed to write to would tell whose it is, as asking for its conversation does: the answer names it.
    connect()
    respx.post("http://saas.test/internal/whatsapp/send").mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    to_a_number = ("/whatsapp_inbox/messages/send", {"to": "600 111 222", "text": "Hola", "client_message_id": "0199e000-0000-7000-8000-0000000000c2"})
    a_notice = ("/whatsapp_inbox/messages/notify", {"phone": ANA, "text": "Hola"})
    as_role("hub_employee")
    for path, payload in (to_a_number, a_notice):
        refused = post(client, path, payload)
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    assert not Message.objects.filter(direction="outbound").exists()
    as_role("hub_owner")
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
        sent = post(client, *to_a_number)
    assert (sent.status_code, sent.json()["conversation_id"]) == (201, str(chats[ANA].id))
    assert post(client, *a_notice).json()["conversation_id"] == str(chats[ANA].id)


def test_a_card_made_from_a_nameless_conversation_takes_the_number_as_its_name_only_from_whoever_sees_it(lacking, as_role, client):
    receive("wamid.1", phone=NAMELESS[1:], contact_name="")
    receive("wamid.2", phone="34699000000", contact_name="")
    ids = {row.phone: str(row.id) for row in Conversation.objects.all()}
    as_role("hub_employee")
    made = post(client, "/whatsapp_inbox/conversations/link_customer", {"id": ids[NAMELESS], "create": True}).json()
    assert (made["display_name"], made["customer_name"], made["phone"]) == (MASKED, MASKED, None)
    as_role("hub_owner")
    made = post(client, "/whatsapp_inbox/conversations/link_customer", {"id": ids["+34699000000"], "create": True}).json()
    assert (made["display_name"], made["customer_name"], made["phone"]) == ("+34699000000",) * 3
    # Both cards keep the number in their phone, which Customers gives only to whoever sees it.
    told_by_customers = {row["name"]: row["phone"] for row in get(client, "/customer/customers").json()["rows"]}
    assert told_by_customers == {MASKED: NAMELESS, "+34699000000": "+34699000000"}


def test_nobody_sorts_the_inbox_by_the_number(chats, as_role, client):
    # The order would tell whose number comes first to whoever does not see the numbers.
    as_role("hub_owner")
    assert get(client, LIST, sort="phone").status_code == 422


def test_the_contact_order_puts_the_nameless_by_their_number_only_for_whoever_sees_it(lacking, as_role, client):
    # Two nameless conversations, the later one with the lower number: by number it comes first, by arrival second.
    receive("wamid.9", phone="34699000000", contact_name="")
    receive("wamid.8", phone="34611000000", contact_name="")

    def phones_in_order() -> list[str]:
        return [row["display_name"] for row in get(client, LIST, sort="contact", dir="asc").json()["rows"]]

    as_role("hub_owner")
    assert phones_in_order() == ["+34611000000", "+34699000000"]
    as_role("hub_employee")
    assert phones_in_order() == ["+346••••0000", "+346••••0000"]
    ids = [row["id"] for row in get(client, LIST, sort="contact", dir="asc").json()["rows"]]
    assert ids == sorted(ids)
