"""What only the public booking page needs: whose page it is (the business's name and the privacy policy its form
links to) and the trap field of its form, which a person never sees and a robot fills in. The customer's personal
link says whose booking it is too: the business's name and its logo."""

import json

import pytest
from django.utils import translation

from apps.appointment.models import Appointment
from apps.customer.models import Customer
from apps.online_booking import public_page
from apps.online_booking.models import Booking, Settings
from apps.online_booking.schemas import PublicBookIn
from base.tenancy.context import use_hub
from base.tests.test_public_door import B_HOST, TOKEN, book_here, door
from config.api import api
from control.models.hubs import Hub

from .conftest import HUB_DB, A, B, booking_data, make_page, no_rule_of_hours, open_salon, public

pytestmark = HUB_DB

#: All the page told a visitor before it said whose it is.
PAGE_FIELDS = {
    "title",
    "welcome_message",
    "primary_color",
    "logo_url",
    "require_email",
    "allow_staff_selection",
    "allow_notes",
    "cancellation_policy",
    "min_booking_notice",
    "max_advance_booking",
    "allow_customer_cancellation",
    "cancellation_notice_hours",
    "timezone",
}
OWNER_FIELDS = {"business_name", "privacy_policy_url"}
#: All her link told her before it said whose booking it is.
BOOKING_FIELDS = {
    "number",
    "status",
    "start",
    "end",
    "timezone",
    "service_names",
    "staff_name",
    "can_cancel",
    "cancel_until",
    "cancellation_policy",
}
LINK_OWNER_FIELDS = {"business_name", "logo_url"}
SPAM = "https://cheap-pills.example"
#: An upload's name, as ``apps.online_booking.logo`` keeps it.
LOGO = "0123456789abcdef.png"


def named(scope, name: str) -> None:
    assert Hub.objects.filter(slug=scope.key).update(name=name) == 1


def test_the_page_names_its_business_and_links_the_privacy_policy(salon, settings):
    settings.SAAS_URL = "https://erplora.com/"
    named(A, "Salón Lucía")
    page = public("page")
    assert (page.business_name, page.privacy_policy_url) == ("Salón Lucía", "https://erplora.com/legal/privacy/")


def test_a_business_registered_without_a_name_is_named_by_nobody(salon):
    named(A, "")
    assert public("page").business_name == ""


def test_the_page_tells_nothing_more_of_the_business_than_whose_it_is(salon):
    named(A, "Salón Lucía")
    assert set(public("page").model_dump()) == PAGE_FIELDS | OWNER_FIELDS
    documented = api.get_openapi_schema()["components"]["schemas"]["online_booking.PageOut"]["properties"]
    assert set(documented) == PAGE_FIELDS | OWNER_FIELDS


def test_each_business_s_page_names_its_own_business(client, hub_b):
    named(A, "Salon A")
    named(B, "Salon B")
    make_page()
    with use_hub(hub_b):
        make_page()
    assert door(client, "online_booking.public.page").json()["business_name"] == "Salon A"
    assert door(client, "online_booking.public.page", host=B_HOST, slug=B.key).json()["business_name"] == "Salon B"


def test_the_trap_field_left_empty_books_as_ever(client, anytime):
    salon = open_salon()
    booked = door(client, "online_booking.public.book", booking_data(salon, website=""))
    assert booked.status_code == 200, booked.content
    assert Appointment.objects.filter(number=booked.json()["number"]).exists()


def test_a_filled_trap_field_books_nothing_and_never_says_why(client, anytime):
    salon = open_salon()
    cards = Customer.objects.count()
    refused = door(
        client, "online_booking.public.book", booking_data(salon, website=SPAM), HTTP_ACCEPT_LANGUAGE="es"
    )
    assert refused.status_code == 422
    error = refused.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error.get("fields", {})) <= {"__all__"}
    assert "website" not in refused.content.decode()
    with translation.override("es"):
        spanish = str(public_page.NOT_TAKEN)
    with translation.override("en"):
        assert error["message"] == spanish != str(public_page.NOT_TAKEN)
    assert not Appointment.objects.exists() and not Booking.objects.exists()
    assert Customer.objects.count() == cards


def test_the_trap_field_is_no_part_of_the_documented_input():
    assert "website" in PublicBookIn.model_fields
    assert "website" not in PublicBookIn.model_json_schema()["properties"]
    documented = api.get_openapi_schema()["components"]["schemas"]["online_booking.PublicBookIn"]["properties"]
    assert "website" not in documented and {"service_ids", "start", "name", "phone"} <= set(documented)


def test_a_trap_field_filled_with_something_that_is_no_text_is_refused_the_same(client, anytime):
    salon = open_salon()
    for filled in (5, [SPAM], {"url": SPAM}):
        refused = door(client, "online_booking.public.book", booking_data(salon, website=filled))
        assert refused.status_code == 422, refused.content
        assert refused.json()["error"]["message"] == str(public_page.NOT_TAKEN)
        assert "website" not in refused.content.decode()
    assert not Appointment.objects.exists() and not Booking.objects.exists()


def booked_with_logo(client) -> tuple[dict, str]:
    """A booking made on the page of «Salón Lucía», whose page then shows :data:`LOGO`; with the address it shows it at."""
    named(A, "Salón Lucía")
    booked = book_here(client, open_salon())
    assert Settings.objects.update(logo=LOGO) == 1
    shown = public("page").logo_url
    assert shown.startswith("/p/media/") and shown.endswith(LOGO)
    return booked, shown


def owner_on(client, operation: str, booked: dict) -> tuple[str, str]:
    """The business's name and logo address the public ``operation`` answers for ``booked``'s link."""
    answer = door(client, f"online_booking.public.{operation}", {"token": booked["token"]})
    assert answer.status_code == 200, answer.content
    return answer.json()["business_name"], answer.json()["logo_url"]


def test_her_link_names_the_business_and_shows_its_logo(client, anytime):
    booked, shown = booked_with_logo(client)
    assert owner_on(client, "booking", booked) == ("Salón Lucía", shown)


def test_her_link_of_a_business_without_a_logo_shows_none(client, anytime):
    named(A, "Salón Lucía")
    booked = book_here(client, open_salon())
    seen = public("booking", {"token": booked["token"]})
    assert (seen.business_name, seen.logo_url) == ("Salón Lucía", "")


def test_her_link_names_the_business_with_the_page_switched_off(client, anytime):
    booked, shown = booked_with_logo(client)
    assert Settings.objects.update(is_enabled=False) == 1
    assert owner_on(client, "booking", booked) == ("Salón Lucía", shown)


def test_her_link_still_names_the_business_once_she_cancels(client, anytime):
    booked, shown = booked_with_logo(client)
    assert owner_on(client, "cancel", booked) == ("Salón Lucía", shown)
    assert public("booking", {"token": booked["token"]}).status == "cancelled"


@pytest.mark.parametrize("operation", ["booking", "cancel"])
def test_a_link_that_does_not_exist_names_no_business(client, anytime, operation):
    _, shown = booked_with_logo(client)
    unknown = door(client, f"online_booking.public.{operation}", {"token": TOKEN})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "online_booking.booking_not_found")
    said = json.dumps(unknown.json(), ensure_ascii=False)
    assert "Salón Lucía" not in said and LOGO not in said and shown not in said
    assert set(unknown.json()) == {"error"}


def test_each_business_s_link_names_its_own_business(client, anytime, hub_b):
    named(A, "Salon A")
    named(B, "Salon B")
    mine = book_here(client, open_salon())
    with use_hub(hub_b):
        no_rule_of_hours()
        salon_b = open_salon()
    theirs = book_here(client, salon_b, host=B_HOST, slug=B.key)
    here = door(client, "online_booking.public.booking", {"token": mine["token"]})
    there = door(client, "online_booking.public.booking", {"token": theirs["token"]}, host=B_HOST, slug=B.key)
    assert (here.json()["business_name"], there.json()["business_name"]) == ("Salon A", "Salon B")


def test_her_link_tells_nothing_more_of_the_business_than_whose_booking_it_is(client, anytime):
    named(A, "Salón Lucía")
    booked = book_here(client, open_salon())
    assert set(public("booking", {"token": booked["token"]}).model_dump()) == BOOKING_FIELDS | LINK_OWNER_FIELDS
    documented = api.get_openapi_schema()["components"]["schemas"]["online_booking.PublicBookingOut"]
    assert set(documented["properties"]) == BOOKING_FIELDS | LINK_OWNER_FIELDS
    assert LINK_OWNER_FIELDS <= set(documented["required"])
