"""A guest's phone and email reach only whoever sees the customers' contact details (``base.view_customer_contact``).
Anyone else gets the reservations and the waitlist by the guest's name, without them, on every door (the API, the
assistant, the live list), and cannot find, filter or sort the book by them.

No basic role lacks the permission today (whoever takes the bookings calls the guests back): these tests take the
employee's and the manager's roles without it, as a role the business makes may be. Every caller is a person signed
in to business A, never a made-up actor."""

import json

import pytest
from django.apps import apps
from django.test import RequestFactory
from live.assistant.running import run_tool
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.reservation.models import Reservation
from base.operations import HubContextBuilder
from base.sensitive import VIEW_CUSTOMER_CONTACT

from .conftest import HOST, HUB_DB, TOMORROW, A, make_entry, make_reservation, open_week

pytestmark = HUB_DB

PHONE = "+34600111222"
EMAIL = "ana@example.com"
DAY = {"date_from": TOMORROW.isoformat(), "date_to": TOMORROW.isoformat()}
SEERS = ["hub_owner", "hub_manager", "hub_employee"]
BOOK = "/reservation/reservations"
WAITLIST = "/reservation/waitlist"


@pytest.fixture
def ana(db):
    return make_reservation(guest_name="Ana García", guest_phone=PHONE, guest_email=EMAIL)


@pytest.fixture
def luis(db):
    return make_entry(guest_name="Luis Pérez", guest_phone="+34600222333", guest_email="luis@example.com")


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


def contact(rows: list[dict]) -> list[tuple]:
    return [(row["guest_name"], row["guest_phone"], row["guest_email"]) for row in rows]


def context_of(user):
    """The context a request of ``user`` to business A gets, as every door builds it."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


# ── What comes out ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", SEERS)
def test_whoever_sees_the_contact_gets_the_guests_phone_and_email(ana, luis, as_role, client, role):
    as_role(role)
    assert contact(get(client, BOOK, **DAY).json()["rows"]) == [("Ana García", PHONE, EMAIL)]
    assert contact([get(client, f"{BOOK}/detail", id=str(ana.id)).json()]) == [("Ana García", PHONE, EMAIL)]
    luis_contact = [("Luis Pérez", "+34600222333", "luis@example.com")]
    assert contact(get(client, WAITLIST).json()["rows"]) == luis_contact
    assert contact([get(client, f"{WAITLIST}/detail", id=str(luis.id)).json()]) == luis_contact


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_without_it_the_book_and_the_waitlist_come_by_the_guests_name_alone(ana, luis, lacking, as_role, client, role):
    as_role(role)
    assert contact(get(client, BOOK, **DAY).json()["rows"]) == [("Ana García", None, None)]
    detail = get(client, f"{BOOK}/detail", id=str(ana.id)).json()
    assert (contact([detail]), detail["party_size"]) == ([("Ana García", None, None)], 2)
    assert contact(get(client, WAITLIST).json()["rows"]) == [("Luis Pérez", None, None)]
    assert contact([get(client, f"{WAITLIST}/detail", id=str(luis.id)).json()]) == [("Luis Pérez", None, None)]


def test_a_guest_booked_under_her_phone_is_said_without_it_to_whoever_lacks_it(lacking, as_role, client):
    # Who books herself by WhatsApp without a name is named by her phone; without the permission, by the day and hour.
    booked = make_reservation(guest_name="", guest_phone=PHONE, source="whatsapp")
    entry = make_entry(guest_name="", guest_phone=PHONE)
    rows = ((BOOK, booked), (WAITLIST, entry))
    as_role("hub_owner")
    said = [get(client, f"{path}/detail", id=str(row.id)).json()["label"] for path, row in rows]
    assert all(label.startswith(f"{PHONE} · ") for label in said)
    as_role("hub_employee")
    without = [get(client, f"{path}/detail", id=str(row.id)).json()["label"] for path, row in rows]
    assert without == [label.removeprefix(f"{PHONE} · ") for label in said]


def test_a_write_answers_without_the_contact_it_keeps(lacking, as_role, client):
    open_week()
    as_role("hub_employee")
    answer = post(client, BOOK, {"guest_name": "Eva Ruiz", "guest_phone": "600 444 555", "guest_email": "eva@example.com",
                                 "date": TOMORROW.isoformat(), "time": "21:00", "party_size": 2})
    assert answer.status_code == 201, answer.content
    assert (answer.json()["guest_phone"], answer.json()["guest_email"]) == (None, None)
    kept = Reservation.objects.get(pk=answer.json()["id"])
    assert (kept.guest_phone, kept.guest_email) == ("+34600444555", "eva@example.com")


def test_the_assistant_gives_the_reservation_without_contact_to_whoever_lacks_it(ana, make_user, monkeypatch):
    employee = make_user("eva", host=A.key, role="hub_employee")

    def told() -> tuple:
        outcome = run_tool(context_of(employee), operation("reservation.reservation.get"), json.dumps({"id": str(ana.id)}))
        assert outcome.outcome == "ok", outcome.content
        answer = json.loads(outcome.content)
        return answer["guest_name"], answer["guest_phone"], answer["guest_email"]

    assert told() == ("Ana García", PHONE, EMAIL)
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert told() == ("Ana García", None, None)


@pytest.mark.parametrize("name", ["reservation.reservation.list", "reservation.waitlist.list"])
def test_the_live_lists_answer_without_contact_to_whoever_lacks_it(ana, luis, make_user, monkeypatch, name):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    employee = make_user("eva", host=A.key, role="hub_employee")
    op = operation(name)

    def rows() -> list[tuple]:
        sub = Subscription(id="book", op=op, params=op.input.model_validate({}))
        frame = executor._run_one(Stream(context_of(employee)), sub).decode()
        return [phone for _, phone, _ in contact(json.loads(frame.split("data: ", 1)[1])["data"]["rows"])]

    assert rows() != [None]
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert rows() == [None]


# ── Finding, filtering and sorting by them ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [BOOK, WAITLIST])
def test_filtering_by_the_guests_phone_is_refused_without_it(ana, luis, lacking, as_role, client, path):
    as_role("hub_employee")
    refused = get(client, path, guest_phone="600")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    as_role("hub_owner")
    assert len(get(client, path, guest_phone="600").json()["rows"]) == 1


@pytest.mark.parametrize("path", [BOOK, WAITLIST])
@pytest.mark.parametrize("sort", ["guest_phone", "-guest_phone"])
def test_the_book_is_not_sorted_by_the_guests_phone(ana, luis, as_role, client, path, sort):
    # The order would tell whose number comes first to whoever does not see the numbers: no one sorts by them.
    as_role("hub_owner")
    assert get(client, path, sort=sort).status_code == 422


@pytest.mark.parametrize("said", ["600 111", "ana@example"])
def test_the_search_looks_into_the_phone_and_email_only_for_whoever_sees_them(ana, lacking, as_role, client, said):
    as_role("hub_owner")
    assert contact(get(client, BOOK, search=said).json()["rows"]) == [("Ana García", PHONE, EMAIL)]
    as_role("hub_employee")
    assert get(client, BOOK, search=said).json()["rows"] == []
    assert contact(get(client, BOOK, search="Ana").json()["rows"]) == [("Ana García", None, None)]


def test_the_waitlist_search_looks_into_the_phone_only_for_whoever_sees_it(luis, lacking, as_role, client):
    as_role("hub_owner")
    assert len(get(client, WAITLIST, search="600 222").json()["rows"]) == 1
    as_role("hub_employee")
    assert get(client, WAITLIST, search="600 222").json()["rows"] == []
    assert len(get(client, WAITLIST, search="Luis").json()["rows"]) == 1


def test_a_reservation_named_by_its_guests_phone_is_found_only_by_whoever_sees_it(ana, lacking, as_role, client):
    as_role("hub_owner")
    assert get(client, f"{BOOK}/detail", guest="600 111 222").json()["id"] == str(ana.id)
    as_role("hub_employee")
    missed = get(client, f"{BOOK}/detail", guest="600 111 222")
    assert (missed.status_code, missed.json()["error"]["code"]) == (404, "reservation.reservation_not_found")
    assert get(client, f"{BOOK}/detail", guest="Ana").json()["id"] == str(ana.id)


def test_a_step_on_a_reservation_named_by_its_guests_phone_is_refused_without_it(ana, lacking, as_role, client):
    as_role("hub_employee")
    missed = post(client, f"{BOOK}/confirm", {"guest": "ana@example.com"})
    assert (missed.status_code, missed.json()["error"]["code"]) == (404, "reservation.reservation_not_found")
    assert Reservation.objects.get(pk=ana.pk).status == "pending"
    as_role("hub_owner")
    assert post(client, f"{BOOK}/confirm", {"guest": "600 111 222"}).json()["status"] == "confirmed"


def test_a_waitlist_entry_named_by_its_guests_phone_is_found_only_by_whoever_sees_it(luis, lacking, as_role, client):
    as_role("hub_owner")
    assert get(client, f"{WAITLIST}/detail", guest="600 222 333").json()["id"] == str(luis.id)
    as_role("hub_employee")
    missed = post(client, f"{WAITLIST}/update", {"guest": "600 222 333", "is_contacted": True})
    assert (missed.status_code, missed.json()["error"]["code"]) == (404, "reservation.entry_not_found")
    assert post(client, f"{WAITLIST}/update", {"guest": "Luis", "is_contacted": True}).json()["is_contacted"] is True
