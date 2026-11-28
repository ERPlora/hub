"""A booking by its personal link, and until when the customer may cancel it."""

import datetime as dt

import pytest
from live.errors import NotFound

from apps.online_booking.models import Booking
from apps.online_booking.queries.links import public_booking
from apps.online_booking.queries.visitors import hash_token
from apps.online_booking.schemas.public import TokenIn

from .conftest import HUB_DB, MONDAY, TUESDAY, at, make_appointment, make_page, make_rules, public, public_ctx

pytestmark = HUB_DB


def test_the_link_shows_the_booking_and_until_when_it_can_be_cancelled(salon):
    make_rules(cancellation_notice_hours=24)
    make_page(cancellation_policy="Cancel 24 h ahead.")
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY + dt.timedelta(days=1), "10:00")
    )
    Booking.objects.create(appointment=appointment, token_hash=hash_token("t" * 43))
    seen = public("booking", {"token": "t" * 43}).model_dump()
    assert seen["number"] == appointment.number
    assert seen["status"] == "confirmed"
    assert seen["service_names"] == "Haircut"
    assert seen["staff_name"] == "Ana López"
    assert seen["can_cancel"] is True
    assert seen["cancel_until"].isoformat() == "2030-03-05T10:00:00+01:00"
    assert seen["cancellation_policy"] == "Cancel 24 h ahead."


def test_past_the_notice_or_without_cancellation_the_link_cannot_cancel(salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "07:00")
    )
    Booking.objects.create(appointment=appointment, token_hash=hash_token("t" * 43))
    make_rules(cancellation_notice_hours=24)
    assert public("booking", {"token": "t" * 43}).can_cancel is False
    make_rules(allow_customer_cancellation=False)
    seen = public_booking(public_ctx(), TokenIn(token="t" * 43))
    assert (seen.can_cancel, seen.cancel_until) == (False, None)


def test_an_unknown_revoked_or_deleted_link_finds_nothing(salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00")
    )
    Booking.objects.create(appointment=appointment, token_hash=None)
    gone = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "11:00"),
        deleted_at=at(MONDAY, "07:00"),
    )
    Booking.objects.create(appointment=gone, token_hash=hash_token("g" * 43))
    for token in ("x" * 43, "g" * 43):
        with pytest.raises(NotFound) as error:
            public("booking", {"token": token})
        assert error.value.code == "online_booking.booking_not_found"
