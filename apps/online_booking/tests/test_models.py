"""The online booking app's tables: the page's settings (one row) and the link of each booking made on the page.

A booking is an appointment of Citas: this app keeps no status, date nor customer of its own, only the hash
of the customer's link and the visitor's fingerprint, both emptied when her data is erased.
"""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.online_booking.models import Booking, Settings

from .conftest import TUESDAY, at, make_appointment

pytestmark = pytest.mark.django_db


def test_the_factory_settings_keep_the_page_off_and_ask_only_for_the_mobile():
    settings = Settings()
    assert settings.is_enabled is False
    assert settings.page_title == ""
    assert settings.welcome_message == ""
    assert settings.primary_color == "#6366f1"
    assert settings.logo_url == ""
    assert settings.require_email is False
    assert settings.max_upcoming_per_customer == 3
    assert settings.allow_staff_selection is True
    assert settings.allow_notes is True
    assert settings.confirmation_message == ""
    assert settings.cancellation_policy == ""


def test_the_settings_are_one_row():
    Settings.objects.create()
    with pytest.raises(IntegrityError), transaction.atomic():
        Settings.objects.create()


def test_ids_are_uuid7():
    assert Settings.objects.create().id.version == 7


def test_a_booking_is_one_appointment_with_the_hash_of_its_link(salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00")
    )
    booking = Booking.objects.create(
        appointment=appointment, token_hash="a" * 64, requester="f" * 64
    )
    assert booking.id.version == 7
    assert booking.created_at is not None
    assert str(booking) == appointment.number
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(appointment=appointment, token_hash="b" * 64)


def test_two_bookings_never_share_a_link_but_many_may_be_revoked(salon):
    first = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00"))
    second = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "11:00"))
    third = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "12:00"))
    Booking.objects.create(appointment=first, token_hash="a" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(appointment=second, token_hash="a" * 64)
    # A revoked link has no hash: any number of them.
    Booking.objects.create(appointment=second, token_hash=None)
    Booking.objects.create(appointment=third, token_hash=None)
    assert Booking.objects.filter(token_hash__isnull=True).count() == 2


def test_an_appointment_with_a_booking_cannot_be_removed_from_under_it(salon):
    from django.db.models import ProtectedError

    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00")
    )
    Booking.objects.create(appointment=appointment, token_hash=uuid.uuid4().hex * 2)
    with pytest.raises(ProtectedError):
        appointment.delete()
