"""The customer's phone and email on an online booking reach only whoever sees the customers' contact details
(``base.view_customer_contact``). Anyone else gets the booking and the customer's name without them, on every door
(the API, the assistant, the live inbox), and cannot find a booking by them: not by the inbox's search, nor its
customer filter, nor by naming the customer by her phone or email. The public booking page does not change.

No basic role lacks the permission today: these tests take it from the employee's and the manager's roles, as a role
the business makes may. Every caller is a person with an account; the employee is Bea, linked to her staff record.
"""

import json

import pytest
from django.apps import apps
from django.test import RequestFactory
from live.assistant.running import run_tool
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.appointment.models import Appointment
from apps.flow.tests.test_api import get, post
from base.operations import HubContextBuilder
from base.sensitive import VIEW_CUSTOMER_CONTACT

from .conftest import HOST, HUB_DB, MONDAY, A, at, booking_data, make_appointment, public

pytestmark = HUB_DB

PHONE = "+34600111222"
EMAIL = "lucia@example.com"
SEEN = ("Lucía Pérez", PHONE, EMAIL)
HIDDEN = ("Lucía Pérez", None, None)


def without_contact(monkeypatch, *roles: str) -> None:
    permissions = apps.get_app_config("base").role_permissions
    for role in roles:
        monkeypatch.setitem(permissions, role, [name for name in permissions[role] if name != VIEW_CUSTOMER_CONTACT])


@pytest.fixture
def lacking(monkeypatch):
    """The employee's and the manager's roles without «View customer contact details»."""
    without_contact(monkeypatch, "hub_employee", "hub_manager")


@pytest.fixture
def beas(salon):
    """Lucía's online booking with Bea, this morning, already past: every step of the inbox applies to it."""
    salon.lucia.email = EMAIL
    salon.lucia.save(update_fields=["email"])
    return make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "07:00"), status="confirmed")


@pytest.fixture
def sign_in(client, make_user, salon):
    """Signs in a person with ``role``; the employee is Bea, linked to her staff record."""

    def signed(role: str):
        user = make_user(role, host=A.key, role=role)
        if role == "hub_employee":
            salon.bea.user = user.person
            salon.bea.save(update_fields=["user"])
        client.force_login(user)
        return user

    return signed


def contact(answer: dict) -> tuple:
    return answer["customer_name"], answer["customer_phone"], answer["customer_email"]


def listed(client, **filters) -> list[tuple]:
    return [contact(row) for row in get(client, "/online_booking/bookings", **filters).json()["rows"]]


def context_of(user):
    """The context the Hub builds for ``user``'s own request: what the assistant and the live inbox run with."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


# ── What comes out ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["hub_owner", "hub_manager", "hub_employee"])
def test_whoever_sees_the_contact_gets_the_customers_phone_and_email_on_the_booking(beas, sign_in, client, role):
    sign_in(role)
    assert listed(client) == [SEEN]
    assert contact(get(client, "/online_booking/bookings/detail", id=str(beas.id)).json()) == SEEN


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_without_it_the_inbox_and_the_booking_come_with_the_customers_name_but_without_her_phone_or_email(
    beas, lacking, sign_in, client, role
):
    sign_in(role)
    assert listed(client) == [HIDDEN]
    assert contact(get(client, "/online_booking/bookings/detail", id=str(beas.id)).json()) == HIDDEN


def test_without_it_a_step_answers_the_booking_without_contact_and_keeps_it(beas, lacking, sign_in, client):
    sign_in("hub_manager")
    done = post(client, "/online_booking/bookings/complete", {"id": str(beas.id)})
    assert (done.status_code, contact(done.json())) == (200, HIDDEN), done.json()
    kept = Appointment.objects.get(pk=beas.id)
    assert (kept.status, kept.customer_phone, kept.customer_email) == ("completed", PHONE, EMAIL)


def test_the_assistant_gives_the_booking_without_contact_to_whoever_lacks_it(beas, make_user, salon, monkeypatch):
    employee = make_user("eva", host=A.key, role="hub_employee")
    salon.bea.user = employee.person
    salon.bea.save(update_fields=["user"])

    def read() -> tuple:
        tool = operation("online_booking.booking.get")
        outcome = run_tool(context_of(employee), tool, json.dumps({"id": str(beas.id)}))
        assert outcome.outcome == "ok", outcome.content
        return contact(json.loads(outcome.content))

    assert read() == SEEN
    without_contact(monkeypatch, "hub_employee")
    assert read() == HIDDEN


def test_the_live_inbox_answers_without_contact_to_whoever_lacks_it(beas, make_user, salon, monkeypatch):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    employee = make_user("eva", host=A.key, role="hub_employee")
    salon.bea.user = employee.person
    salon.bea.save(update_fields=["user"])

    def rows() -> list[tuple]:
        op = operation("online_booking.booking.list")
        sub = Subscription(id="inbox", op=op, params=op.input.model_validate({}))
        frame = executor._run_one(Stream(context_of(employee)), sub).decode()
        return [contact(row) for row in json.loads(frame.split("data: ", 1)[1])["data"]["rows"]]

    assert rows() == [SEEN]
    without_contact(monkeypatch, "hub_employee")
    assert rows() == [HIDDEN]


def test_the_public_page_still_books_and_answers_the_customer_as_before(salon, lacking):
    booked = public("book", booking_data(salon))
    mine = public("booking", {"token": booked.token})
    assert (booked.number, mine.number, mine.status) == (booked.number, booked.number, booked.status)
    kept = Appointment.objects.get(number=booked.number)
    assert (kept.customer_phone, kept.customer_email) == ("+34612345678", "marta@example.com")


# ── Finding a booking by them ─────────────────────────────────────────────────────────────────────────────────────

#: The phone or the email as a person types them: in the inbox's search, any part of them; in its customer filter,
#: the whole number however it is written, or the whole address.
TYPED = [
    *[("search", typed) for typed in ("600111222", "600 111", PHONE, EMAIL, "lucia@", "example.com")],
    *[("customer_name", typed) for typed in ("600111222", "600 111 222", PHONE, EMAIL)],
]


@pytest.mark.parametrize(("field", "typed"), TYPED)
def test_whoever_sees_the_contact_finds_the_booking_by_her_phone_or_email(beas, sign_in, client, field, typed):
    sign_in("hub_manager")
    assert listed(client, **{field: typed}) == [SEEN]


@pytest.mark.parametrize(("field", "typed"), TYPED)
def test_without_it_the_inbox_finds_nobody_by_her_phone_or_email(beas, lacking, sign_in, client, field, typed):
    sign_in("hub_manager")
    assert listed(client, **{field: typed}) == []
    assert listed(client, **{field: "Lucía"}) == [HIDDEN]


#: Every step of the inbox that names a booking, each with the state it applies to: by its customer and its day.
STEPS = [
    ("GET", "/online_booking/bookings/detail", "confirmed"),
    ("POST", "/online_booking/bookings/confirm", "pending"),
    ("POST", "/online_booking/bookings/complete", "confirmed"),
    ("POST", "/online_booking/bookings/no_show", "confirmed"),
    ("POST", "/online_booking/bookings/cancel", "confirmed"),
    ("POST", "/online_booking/bookings/delete", "confirmed"),
]


@pytest.fixture
def deleting_manager(monkeypatch):
    """The manager also deletes bookings (and their appointments), so every step is theirs to take."""
    for label, permission in (("online_booking", "online_booking.delete_booking"), ("appointment", "appointment.delete_appointment")):
        roles = apps.get_app_config(label).role_permissions
        monkeypatch.setitem(roles, "hub_manager", [*roles["hub_manager"], permission])


def take(client, method: str, path: str, reference: str):
    data = {"customer": reference, "date": MONDAY.isoformat()}
    return get(client, path, **data) if method == "GET" else post(client, path, data)


@pytest.mark.usefixtures("deleting_manager")
@pytest.mark.parametrize("reference", [PHONE, "600 111 222", EMAIL])
@pytest.mark.parametrize(("method", "path", "status"), STEPS)
def test_a_phone_or_an_email_names_the_booking_only_to_whoever_sees_the_contact(
    beas, sign_in, client, monkeypatch, reference, method, path, status
):
    Appointment.objects.filter(pk=beas.id).update(status=status)
    sign_in("hub_manager")
    with monkeypatch.context() as hidden:
        without_contact(hidden, "hub_manager")
        refused = take(client, method, path, reference)
        assert (refused.status_code, refused.json()["error"]["code"]) == (404, "online_booking.booking_not_found")
        kept = Appointment.objects.get(pk=beas.id)
        assert (kept.status, kept.deleted_at) == (status, None)
    answer = take(client, method, path, reference)
    assert answer.status_code == 200, answer.json()
