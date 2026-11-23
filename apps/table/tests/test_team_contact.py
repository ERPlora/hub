"""Who serves a table never shows a colleague's email (BASE-F119, TABLE-F09).

erplora.com names an account without a name by its address, and an account may also have its email and no name. A
colleague's address only reaches whoever sees the team's contact details, so Tables names whoever seats a table by
the part before the «@», on every door: the floor plan and the table's window, the checks and their detail, the waiter
filter (its names and its search), the live screens and the assistant. A named person keeps their name. An employee
sees no colleague's contact details; the manager reads the same name. The checks saved with an address before are
cleaned once by the app's migration (``test_migrations``).
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from live.assistant.running import run_tool
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.table.models import TableSession
from base.models import Membership
from base.operations import HubContextBuilder
from base.services.sessions import ensure_hub_user

from .conftest import HOST, HUB_DB, A, make_table

pytestmark = HUB_DB

ADDRESS = "bea.lopez@example.com"
#: How Tables names her: what goes before the «@».
SHOWN = "bea.lopez"


def signed_in(username: str, role: str = "hub_employee", **account):
    """A person of business A with ``role``, on their own device: ``(user, client)``."""
    user = get_user_model().objects.create_user(username=username, password="pw", **account)
    Membership.objects.create(user=user, host=A.key, role=role)
    ensure_hub_user(user)
    client = Client()
    client.force_login(user)
    return user, client


#: The two ways an account reaches the Hub without a name: named by its address, or with its email and no name.
NAMELESS = [{"first_name": ADDRESS, "email": ADDRESS}, {"email": ADDRESS}]


@pytest.fixture(params=NAMELESS, ids=["named-by-address", "email-only"])
def seated_by_bea(request, db):
    """Table 4, seated by Bea, a waiter whose account has no name of its own: the check's id."""
    make_table("4")
    _, bea = signed_in("bea", **request.param)
    seated = post(bea, "/table/sessions/open", {"table": "4", "guests_count": 2})
    assert seated.status_code == 201, seated.content
    return seated.json()["id"]


def context_of(user):
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_a_colleague_without_a_name_who_seats_a_table_is_named_without_their_address(seated_by_bea, role):
    _, client = signed_in("reader", role)
    checks = [row["waiter_name"] for row in get(client, "/table/sessions").json()["rows"]]
    detail = get(client, "/table/sessions/detail", id=seated_by_bea).json()["waiter_name"]
    plan = [row["waiter_name"] for row in get(client, "/table/tables").json()["rows"] if row["number"] == "4"]
    window = get(client, "/table/tables/detail", table="4").json()["waiter_name"]
    waiters = [row["name"] for row in get(client, "/table/waiters").json()["rows"]]
    assert (checks, detail, plan, window, waiters) == ([SHOWN], SHOWN, [SHOWN], SHOWN, [SHOWN])
    assert TableSession.objects.get(pk=seated_by_bea).waiter_name == SHOWN


def test_the_waiter_filter_cannot_be_searched_by_their_address(seated_by_bea):
    _, ana = signed_in("ana")
    assert get(ana, "/table/waiters", search="example.com").json()["rows"] == []
    assert [row["name"] for row in get(ana, "/table/waiters", search="bea").json()["rows"]] == [SHOWN]


def test_nor_on_the_live_plan_or_by_the_assistant(seated_by_bea, monkeypatch):
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    ana, _ = signed_in("ana")
    op = operation("table.table.list")
    sub = Subscription(id="floor", op=op, params=op.input.model_validate({}))
    frame = executor._run_one(Stream(context_of(ana)), sub).decode()
    live = [row["waiter_name"] for row in json.loads(frame.split("data: ", 1)[1])["data"]["rows"] if row["number"] == "4"]
    outcome = run_tool(context_of(ana), operation("table.waiter.list"), "{}")
    assert outcome.outcome == "ok", outcome.content
    assert (live, [row["name"] for row in json.loads(outcome.content)["rows"]]) == ([SHOWN], [SHOWN])


def test_a_named_colleague_keeps_their_name(db):
    make_table("4")
    _, luis = signed_in("luis", first_name="Luis", last_name="García", email="luis@example.com")
    seated = post(luis, "/table/sessions/open", {"table": "4", "guests_count": 2})
    assert (seated.status_code, seated.json()["waiter_name"]) == (201, "Luis García"), seated.content
