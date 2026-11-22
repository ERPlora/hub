"""The customer's phone and email on an appointment reach only whoever sees the customers' contact details
(``base.view_customer_contact``). Anyone else gets the appointment and the customer's name without them, on every door
(the API, the assistant, the live agenda), and cannot name a customer by her phone or email to book, list or move her
appointments.

No basic role that opens the agenda lacks the permission today: these tests take it from the employee's and the
manager's roles, as a role the business makes may. Every caller is a person with an account and, for the employee, her
own staff record: a caller that is no person reads the appointments as the customer does.
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

from .conftest import HOST, HUB_DB, MONDAY, A, at, make_appointment, wall

pytestmark = HUB_DB

PHONE = "+34600111222"
EMAIL = "lucia@example.com"
SEEN = ("Lucía Pérez", PHONE, EMAIL)
HIDDEN = ("Lucía Pérez", None, None)


@pytest.fixture
def lucia(salon):
    salon.lucia.email = EMAIL
    salon.lucia.save(update_fields=["email"])
    return salon.lucia


@pytest.fixture
def beas(salon, lucia):
    """Lucía's appointment with Bea, the employee who signs in."""
    return make_appointment(lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"), notes="Bring the photo")


@pytest.fixture
def lacking(monkeypatch):
    """The employee's and the manager's roles without «View customer contact details»."""
    roles = apps.get_app_config("base").role_permissions
    for role in ("hub_employee", "hub_manager"):
        monkeypatch.setitem(roles, role, [name for name in roles[role] if name != VIEW_CUSTOMER_CONTACT])


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


def context_of(user):
    """The context the Hub builds for ``user``'s own request: what the assistant and the live agenda run with."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    return HubContextBuilder().from_request(request)


# ── What comes out ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["hub_owner", "hub_manager", "hub_employee"])
def test_whoever_sees_the_contact_gets_the_customers_phone_and_email_on_the_appointment(beas, sign_in, client, role):
    sign_in(role)
    assert contact(get(client, "/appointment/appointments/detail", id=str(beas.id)).json()) == SEEN


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_without_it_the_appointment_comes_with_the_customers_name_but_without_her_phone_or_email(
    beas, lacking, sign_in, client, role
):
    sign_in(role)
    answer = get(client, "/appointment/appointments/detail", id=str(beas.id)).json()
    assert (contact(answer), answer["notes"]) == (HIDDEN, "Bring the photo")


def test_without_it_a_write_answers_the_appointment_without_contact_and_keeps_it(beas, lacking, sign_in, client):
    sign_in("hub_employee")
    edited = post(client, "/appointment/appointments/update", {"id": str(beas.id), "notes": "Bring two photos"})
    assert (edited.status_code, contact(edited.json())) == (200, HIDDEN)
    kept = Appointment.objects.get(pk=beas.id)
    assert (kept.notes, kept.customer_phone, kept.customer_email) == ("Bring two photos", PHONE, EMAIL)


@pytest.mark.usefixtures("anytime")
def test_without_it_booking_one_or_several_answers_them_without_contact(salon, lucia, lacking, sign_in, client):
    sign_in("hub_employee")
    booking = {"customer_id": str(lucia.id), "services": [{"service": "Haircut"}], "staff": "Bea"}
    one = post(client, "/appointment/appointments", {**booking, "start": wall(MONDAY, "12:00")})
    several = post(
        client,
        "/appointment/appointments/bulk_create",
        {**booking, "starts": [wall(MONDAY, "13:00"), wall(MONDAY, "14:00")]},
    )
    assert (one.status_code, contact(one.json())) == (201, HIDDEN), one.json()
    assert [contact(row) for row in several.json()["rows"]] == [HIDDEN, HIDDEN], several.json()


def test_the_assistant_gives_the_appointment_without_contact_to_whoever_lacks_it(beas, make_user, salon, monkeypatch):
    employee = make_user("eva", host=A.key, role="hub_employee")
    salon.bea.user = employee.person
    salon.bea.save(update_fields=["user"])

    def read() -> tuple:
        outcome = run_tool(context_of(employee), operation("appointment.appointment.get"), json.dumps({"id": str(beas.id)}))
        assert outcome.outcome == "ok", outcome.content
        return contact(json.loads(outcome.content))

    assert read() == SEEN
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert read() == HIDDEN


def test_the_live_agenda_answers_the_appointment_without_contact_to_whoever_lacks_it(
    beas, make_user, salon, monkeypatch
):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    employee = make_user("eva", host=A.key, role="hub_employee")
    salon.bea.user = employee.person
    salon.bea.save(update_fields=["user"])

    def read() -> tuple:
        op = operation("appointment.appointment.get")
        sub = Subscription(id="appointment", op=op, params=op.input.model_validate({"id": str(beas.id)}))
        frame = executor._run_one(Stream(context_of(employee)), sub).decode()
        return contact(json.loads(frame.split("data: ", 1)[1])["data"])

    assert read() == SEEN
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert read() == HIDDEN


# ── Naming a customer by her phone or her email ───────────────────────────────────────────────────────────────────


def named_by(reference: str, beas) -> list[tuple[str, str, dict]]:
    """Every request of the agenda that names a customer, by ``reference``: listing her appointments, booking one,
    several or a repeating one, and moving or cancelling one as she asks."""
    booking = {"customer": reference, "services": [{"service": "Haircut"}], "staff": "Bea"}
    return [
        ("GET", "/appointment/appointments/for_customer", {"customer": reference}),
        ("POST", "/appointment/appointments", {**booking, "start": wall(MONDAY, "12:00")}),
        ("POST", "/appointment/appointments/bulk_create", {**booking, "starts": [wall(MONDAY, "13:00")]}),
        (
            "POST",
            "/appointment/recurring",
            {**booking, "frequency": "weekly", "start_date": MONDAY.isoformat(), "time": "16:00", "max_occurrences": 2},
        ),
        (
            "POST",
            "/appointment/appointments/reschedule",
            {"id": str(beas.id), "start": wall(MONDAY, "17:00"), "on_behalf_of_customer": True, "customer": reference},
        ),
        (
            "POST",
            "/appointment/appointments/cancel",
            {"id": str(beas.id), "on_behalf_of_customer": True, "customer": reference},
        ),
    ]


def ask(client, method: str, path: str, data: dict):
    return get(client, path, **data) if method == "GET" else post(client, path, data)


@pytest.mark.usefixtures("anytime")
@pytest.mark.parametrize("reference", [PHONE, "600 111 222", EMAIL])
def test_whoever_sees_the_contact_names_the_customer_by_her_phone_or_email(beas, sign_in, client, reference):
    sign_in("hub_employee")
    answers = [ask(client, *request) for request in named_by(reference, beas)]
    assert [answer.status_code for answer in answers] == [200, 201, 201, 201, 200, 200], [a.json() for a in answers]


@pytest.mark.usefixtures("anytime")
@pytest.mark.parametrize("reference", [PHONE, "600 111 222", EMAIL])
def test_without_it_a_phone_or_an_email_names_no_customer(beas, lacking, sign_in, client, reference):
    sign_in("hub_employee")
    answers = [ask(client, *request) for request in named_by(reference, beas)]
    assert [(answer.status_code, answer.json()["error"]["code"]) for answer in answers] == [
        (404, "customer.customer_unavailable")
    ] * 6
    assert [(kept.id, kept.status) for kept in Appointment.objects.filter(customer=beas.customer)] == [(beas.id, beas.status)]
