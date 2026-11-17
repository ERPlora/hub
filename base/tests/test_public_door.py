"""The hub's public door (``/p/<slug>/…`` of its own host): the pages an app gives the business's customers, without a
session — today Online booking's ``/p/<slug>/book``.

The page is the SPA's HTML, whose route of that path paints it, and its calls go through ``POST
/p/<slug>/api/<operation>``, run in this process as nobody signed in, holding only the page's permission. The business
is the host's, never the address: another business's slug on this host, or this one's on another host, is not found and
shows nothing of either.
"""

import hashlib
import hmac
import json

import pytest
from django.apps import apps
from django.core import checks
from django.test import Client

from apps.appointment.models import Appointment
from apps.online_booking.models import Booking
from apps.online_booking.tests.conftest import TUESDAY, anytime, booking_data, clock, make_page, open_salon
from base import activation
from base.models import AppActivation
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, A, B, in_business_a
from base.tests.test_spa import csp_directives, csp_nonce, json_block

#: Fixtures of Online booking's tests: business A entered, its clock stood still, and the hours of its diary open.
__all__ = ["anytime", "clock", "in_business_a"]

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "hub_a", "hub_b")]
B_HOST = f"{B.key}.localhost"
PAGE = f"/p/{A.key}/book"


def door(client, operation: str, data: dict | None = None, *, host: str = HOST, slug: str = A.key, **headers):
    """A call of the page through the door, as its script makes it: the input as the JSON body."""
    return client.post(
        f"/p/{slug}/api/{operation}",
        json.dumps(data or {}),
        content_type="application/json",
        HTTP_HOST=host,
        **headers,
    )


def turn_off(hub, label: str = "online_booking") -> None:
    with use_hub(hub):
        assert AppActivation.objects.filter(host=hub.slug, app=label).update(state="off", chosen=False) == 1
    activation.forget(hub.slug)


# The page


def test_the_booking_page_is_the_shell_for_a_visitor_without_a_session(client):
    response = client.get(PAGE, HTTP_HOST=HOST, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    _, me = json_block(response, "session-me")
    assert (me["user"], me["permissions"]) == (None, [])
    # A visitor has no session to read the business's money with: the page gets it here, for its prices.
    _, door_block = json_block(response, "public-door")
    assert door_block == {"currency": "EUR", "currency_decimals": 2}
    assert "no-store" in response["Cache-Control"]


def test_its_content_security_policy_is_the_shell_s_strict_one(client):
    page = client.get(PAGE, HTTP_HOST=HOST)
    shell = client.get("/demo/items", HTTP_HOST=HOST)

    def policy(response) -> dict[str, str]:
        nonce = csp_nonce(response)
        return {name: value.replace(nonce, "<nonce>") for name, value in csp_directives(response).items()}

    assert policy(page) == policy(shell)
    assert "'unsafe-inline'" not in policy(page)["script-src"]


@pytest.mark.parametrize(
    ("path", "host"),
    [(f"/p/{B.key}/book", HOST), (PAGE, B_HOST), (f"/p/{A.key}/nothing", HOST), (f"/p/{A.key}/media", HOST)],
)
def test_another_business_s_page_or_one_no_app_gives_is_not_found(client, path, host):
    response = client.get(path, HTTP_HOST=host, HTTP_ACCEPT="text/html")
    assert response.status_code == 404
    assert b"session-me" not in response.content


def test_a_business_that_turned_online_booking_off_has_no_page(client, hub_a):
    turn_off(hub_a)
    assert client.get(PAGE, HTTP_HOST=HOST).status_code == 404
    refused = door(client, "online_booking.public.page")
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "not_found")


def test_the_page_is_read_never_posted(client):
    assert client.post(PAGE, HTTP_HOST=HOST).status_code == 405


def test_an_app_opens_a_page_only_with_a_permission_of_its_own(client, monkeypatch):
    # The door hands its permission to anybody: an app may not hand out another's.
    monkeypatch.setattr(apps.get_app_config("demo"), "public_pages", {"steal": "online_booking.public"}, raising=False)
    assert client.get(f"/p/{A.key}/steal", HTTP_HOST=HOST).status_code == 404


# The calls


def test_a_visitor_reads_the_page_its_services_and_free_times_and_books(client, anytime):
    salon = open_salon()
    page = door(client, "online_booking.public.page")
    assert (page.status_code, page.json()["title"]) == (200, "Book an appointment")
    assert "no-store" in page["Cache-Control"]
    services = door(client, "online_booking.public.services", {"limit": 100})
    assert [row["name"] for row in services.json()["rows"]] == ["Colour", "Haircut"]
    slots = door(
        client, "online_booking.public.slots", {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()}
    )
    assert slots.status_code == 200 and slots.json()["slots"]
    booked = door(client, "online_booking.public.book", booking_data(salon, "10:00"))
    assert booked.status_code == 200, booked.content
    appointment = Appointment.objects.get(number=booked.json()["number"])
    assert (appointment.source, appointment.created_by) == ("online", "online booking")
    assert len(booked.json()["token"]) >= 43


def test_the_visitor_is_the_request_s_last_forwarded_address(client, anytime, settings):
    salon = open_salon()
    booked = door(
        client,
        "online_booking.public.book",
        booking_data(salon, "10:00"),
        HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.9",
    )
    assert booked.status_code == 200, booked.content
    fingerprint = hmac.new(settings.SECRET_KEY.encode(), b"203.0.113.9", hashlib.sha256).hexdigest()
    assert Booking.objects.get(appointment__number=booked.json()["number"]).requester == fingerprint


def test_a_signed_in_person_books_as_the_visitor_never_as_themselves(client, make_user, anytime):
    client.force_login(make_user("boss", host=A.key, role="hub_owner"))
    salon = open_salon()
    booked = door(client, "online_booking.public.book", booking_data(salon, "10:00"))
    assert booked.status_code == 200, booked.content
    assert Appointment.objects.get(number=booked.json()["number"]).created_by == "online booking"


@pytest.mark.parametrize(
    "operation",
    ["online_booking.settings.get", "online_booking.booking.list", "base.business.get", "online_booking.nothing"],
)
def test_the_door_runs_only_the_page_s_public_operations(client, make_user, operation):
    # Not even for whoever runs the business: the door holds the page's permission and nothing else.
    client.force_login(make_user("boss", host=A.key, role="hub_owner"))
    make_page()
    refused = door(client, operation)
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "not_found")


def test_another_business_s_slug_or_host_reads_nothing_of_it(client, hub_b):
    make_page(page_title="Salon A")
    with use_hub(hub_b):
        make_page(page_title="Salon B")
    assert door(client, "online_booking.public.page").json()["title"] == "Salon A"
    for host, slug in ((HOST, B.key), (B_HOST, A.key)):
        refused = door(client, "online_booking.public.page", host=host, slug=slug)
        assert (refused.status_code, refused.json()["error"]["code"]) == (404, "not_found")
        assert "Salon" not in refused.content.decode()
    assert door(client, "online_booking.public.page", host=B_HOST, slug=B.key).json()["title"] == "Salon B"


def test_a_refusal_is_the_envelope_in_the_visitor_s_language(client):
    # No settings saved yet: the page is off.
    refused = door(client, "online_booking.public.page", HTTP_ACCEPT_LANGUAGE="es")
    assert refused.status_code == 404
    assert refused.json()["error"] == {
        "code": "online_booking.page_disabled",
        "message": "Este negocio no acepta reservas online ahora mismo.",
    }


def test_a_field_refused_is_the_422_envelope_with_its_field(client, anytime):
    salon = open_salon()
    refused = door(client, "online_booking.public.book", booking_data(salon, phone="12"))
    assert (refused.status_code, set(refused.json()["error"]["fields"])) == (422, {"phone"})
    missing = door(client, "online_booking.public.book", {})
    assert missing.status_code == 422
    assert {"service_ids", "start", "name", "phone"} <= set(missing.json()["error"]["fields"])
    broken = client.post(
        f"/p/{A.key}/api/online_booking.public.page", "{", content_type="application/json", HTTP_HOST=HOST
    )
    assert (broken.status_code, broken.json()["error"]["code"]) == (422, "invalid_payload")


def test_a_call_is_posted_with_the_page_s_csrf_token(hub_a):
    make_page()
    assert Client().get(f"/p/{A.key}/api/online_booking.public.page", HTTP_HOST=HOST).status_code == 405
    forged = Client(enforce_csrf_checks=True).post(
        f"/p/{A.key}/api/online_booking.public.page", "{}", content_type="application/json", HTTP_HOST=HOST
    )
    assert forged.status_code == 403


# What an app declares, said at start (base.E020)


def page_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E020"]


def test_the_pages_of_every_app_are_sound():
    assert page_errors() == []


@pytest.mark.parametrize(
    ("declared", "why"),
    [
        ({"steal": "online_booking.public"}, "not a permission of demo's own"),
        ({"items": "demo.nothing"}, "not a permission of demo's own"),
        ({"book": "demo.view"}, "online_booking gives it too"),
        (["items"], "is not a dict"),
        ({"items": None}, "is not a dict"),
    ],
)
def test_a_page_that_opens_nothing_is_said_at_start(monkeypatch, declared, why):
    # Such a page is left out, or hides another's: nobody would see why its address is not found.
    monkeypatch.setattr(apps.get_app_config("demo"), "public_pages", declared, raising=False)
    errors = [error for error in page_errors() if error.obj.label == "demo"]
    assert len(errors) == 1
    assert why in errors[0].msg


def test_a_page_two_apps_give_is_nobody_s(client, monkeypatch):
    # Which app's it is would hang on the order they are installed in: neither opens it.
    monkeypatch.setattr(apps.get_app_config("demo"), "public_pages", {"book": "demo.view"}, raising=False)
    assert client.get(PAGE, HTTP_HOST=HOST).status_code == 404
