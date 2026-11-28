"""Who sent a ticket, and who did something on the kitchen's History, never shows a colleague's email (BASE-F119).

erplora.com names an account without a name by its address, and an account may also have its email and no name.
A colleague's address only reaches whoever sees the team's contact details, so Kitchen names that person by the part
before the «@», on every door (the route, the live screens, the assistant, the device's notice and the paper), for a
round fired from the till, sent from the kitchen or made by hand, and for a ticket saved with an address before.
A named person keeps their name. An employee sees no colleague's contact details: those readers are employees.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from live.assistant.running import run_tool
from live.context import system_context
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.kitchen.models.tickets import Ticket
from base.models import Membership
from base.operations import HubContextBuilder
from base.schemas.home import NoticeListIn
from base.services.sessions import ensure_hub_user

from .conftest import HOST, HUB_DB, A, run

pytestmark = HUB_DB

ADDRESS = "bea.lopez@example.com"
#: How Kitchen names her: what goes before the «@».
SHOWN = "bea.lopez"


def signed_in(username: str, role: str = "hub_employee", **account):
    """A person of business A with ``role``, as their own device: ``(user, client)``."""
    user = get_user_model().objects.create_user(username=username, password="pw", **account)
    Membership.objects.create(user=user, host=A.key, role=role)
    ensure_hub_user(user)
    client = Client()
    client.force_login(user)
    return user, client


#: The two ways an account reaches the Hub without a name: named by its address, or with its email and no name.
NAMELESS = [{"first_name": ADDRESS, "email": ADDRESS}, {"email": ADDRESS}]


@pytest.fixture(params=NAMELESS, ids=["named-by-address", "email-only"])
def bea(request):
    """Bea, a waiter whose account has no name of its own."""
    return signed_in("bea", **request.param)


@pytest.fixture
def ana():
    """Ana, another employee: she does not see the team's contact details."""
    return signed_in("ana")


@pytest.fixture
def burger(product):
    return product("Burger", "BURGER")


def by_order(client, order_id) -> list[str]:
    answer = get(client, "/kitchen/tickets/by_order", order_id=order_id)
    assert answer.status_code == 200, answer.content
    return [ticket["waiter"] for ticket in answer.json()["tickets"]]


def fired_by(client) -> str:
    """A check with a burger that ``client``'s person opens and fires from the till; its id."""
    opened = post(client, "/sale/orders", {"label": "Table 4", "lines": [{"product": "BURGER"}]})
    assert opened.status_code == 201, opened.content
    fired = post(client, "/sale/orders/fire", {"order_id": opened.json()["id"]})
    assert fired.status_code == 200, fired.content
    return opened.json()["id"]


def context_of(user):
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


# ── What is saved from now on ───────────────────────────────────────────────────────────────────────────────────────


def test_a_round_a_colleague_fires_names_them_without_their_address_before_and_after_it_is_saved(burger, bea, ana):
    order_id = fired_by(bea[1])
    assert by_order(ana[1], order_id) == [SHOWN]
    run("kitchen.ticket.sync", {}, system_context(A))
    assert Ticket.objects.get().waiter == SHOWN
    assert by_order(ana[1], order_id) == [SHOWN]


def test_the_round_sales_tells_the_kitchen_names_them_without_it(burger, bea):
    from live.models import OutboxEvent

    fired_by(bea[1])
    assert OutboxEvent.objects.get(name="sale.order.fired").payload["waiter"] == SHOWN


def test_a_round_a_colleague_sends_from_the_kitchen_names_them_without_it(burger, bea, ana):
    opened = post(bea[1], "/sale/orders", {"label": "Table 4", "lines": [{"product": "BURGER"}]})
    sent = post(bea[1], "/kitchen/tickets/send", {"order_id": opened.json()["id"]})
    assert (sent.status_code, sent.json()["waiter"]) == (201, SHOWN), sent.content
    assert get(ana[1], "/kitchen/tickets/detail", ticket_id=sent.json()["id"]).json()["waiter"] == SHOWN
    assert Ticket.objects.get(pk=sent.json()["id"]).waiter == SHOWN


def test_a_ticket_a_colleague_makes_by_hand_names_them_without_it(bea, ana):
    made = post(bea[1], "/kitchen/tickets", {"items": [{"name": "Staff meal"}]})
    assert made.status_code == 201, made.content
    assert get(ana[1], "/kitchen/tickets/detail", ticket_id=made.json()["id"]).json()["waiter"] == SHOWN
    assert Ticket.objects.get(pk=made.json()["id"]).waiter == SHOWN


def test_the_history_names_who_did_each_thing_without_their_address(bea, ana):
    made = post(bea[1], "/kitchen/tickets", {"items": [{"name": "Staff meal"}]})
    assert post(bea[1], "/kitchen/items/bump", {"ticket_id": made.json()["id"]}).status_code == 200
    rows = get(ana[1], "/kitchen/log").json()["rows"]
    assert rows and {row["actor"] for row in rows} == {SHOWN}


def test_a_named_colleague_keeps_their_name(burger, ana):
    _, luis = signed_in("luis", first_name="Luis", last_name="García", email="luis@example.com")
    assert by_order(ana[1], fired_by(luis)) == ["Luis García"]


# ── A ticket saved with an address before ───────────────────────────────────────────────────────────────────────────


@pytest.fixture
def saved_with_an_address(burger):
    """A ticket Kitchen saved before, when it kept the address of a waiter without a name."""
    _, marta = signed_in("marta", "hub_manager", first_name="Marta")
    opened = post(marta, "/sale/orders", {"label": "Table 4", "lines": [{"product": "BURGER"}]})
    ticket = post(marta, "/kitchen/tickets/send", {"order_id": opened.json()["id"]}).json()
    Ticket.objects.filter(pk=ticket["id"]).update(waiter=ADDRESS)
    return opened.json()["id"], ticket["id"]


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_it_is_read_without_the_address_by_the_route(saved_with_an_address, role):
    order_id, ticket_id = saved_with_an_address
    _, client = signed_in("reader", role)
    detail = get(client, "/kitchen/tickets/detail", ticket_id=ticket_id).json()["waiter"]
    board = [ticket["waiter"] for ticket in get(client, "/kitchen/board").json()["cooking"]]
    assert (detail, board, by_order(client, order_id)) == (SHOWN, [SHOWN], [SHOWN])


def test_on_the_live_display_and_by_the_assistant(saved_with_an_address, ana, monkeypatch):
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    order_id, _ = saved_with_an_address
    op = operation("kitchen.ticket.by_order")
    sub = Subscription(id="kitchen", op=op, params=op.input.model_validate({"order_id": order_id}))
    frame = executor._run_one(Stream(context_of(ana[0])), sub).decode()
    live = [ticket["waiter"] for ticket in json.loads(frame.split("data: ", 1)[1])["data"]["tickets"]]
    outcome = run_tool(context_of(ana[0]), op, json.dumps({"order_id": order_id}))
    assert outcome.outcome == "ok", outcome.content
    assert (live, [ticket["waiter"] for ticket in json.loads(outcome.content)["tickets"]]) == ([SHOWN], [SHOWN])


def test_on_the_device_s_notice(saved_with_an_address, ana, monkeypatch):
    monkeypatch.setattr(
        "base.queries.home.active_apps", lambda scope: frozenset({"base", "kitchen", "sale", "inventory"})
    )
    notices = operation("base.notice.list")(context_of(ana[0]), NoticeListIn()).model_dump(mode="json")["notices"]
    bodies = [notice["body"] for notice in notices]
    assert bodies and not [body for body in bodies if "@" in body]
    assert any(SHOWN in body for body in bodies)


def test_nor_on_its_reprint(saved_with_an_address, ana, printers):
    from apps.printing.models import PrintJob

    _, ticket_id = saved_with_an_address
    reprinted = post(ana[1], "/kitchen/tickets/reprint", {"ticket_id": ticket_id})
    assert reprinted.status_code == 200, reprinted.content
    assert [job.document["waiter"] for job in PrintJob.objects.all()] == [SHOWN]
