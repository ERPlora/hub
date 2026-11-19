"""What only the public booking page needs: whose page it is (the business's name and the privacy policy its form
links to) and the trap field of its form, which a person never sees and a robot fills in."""

from django.utils import translation

from apps.appointment.models import Appointment
from apps.customer.models import Customer
from apps.online_booking import public_page
from apps.online_booking.models import Booking
from apps.online_booking.schemas import PublicBookIn
from base.tenancy.context import use_hub
from base.tests.test_public_door import B_HOST, door
from config.api import api
from control.models import Hub

from .conftest import HUB_DB, A, B, booking_data, make_page, open_salon, public

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
SPAM = "https://cheap-pills.example"


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
