"""The inbox over the diary's online appointments: its list, one booking by its number or as a person says it, and who
sees which (the diary's rule: the employee, her own agenda)."""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from live.errors import Conflict, NotFound, PermissionDenied

from apps.online_booking.models import Booking
from apps.online_booking.queries.bookings import list_bookings
from apps.online_booking.schemas.bookings import BookingListIn
from base.services.sessions import ensure_hub_user

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, MONDAY, TUESDAY, at, ctx_for, make_appointment, make_customer, run

pytestmark = HUB_DB


def listed(data: dict | None = None, **ctx) -> dict:
    return list_bookings(ctx_for(**ctx), BookingListIn.model_validate(data or {})).model_dump()


def numbers(page: dict) -> list[str]:
    return [row["number"] for row in page["rows"]]


@pytest.fixture
def inbox(salon, clock):
    """Three online bookings booked one after another (two on the page), a counter one and a deleted one."""
    marta = make_customer("Marta Gil", phone="+34612345678", email="marta@example.com")
    clock.set(at(MONDAY, "07:00"))
    first = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        number="APT-1",
        status="pending",
    )
    Booking.objects.create(appointment=first, token_hash="1" * 64)
    clock.set(at(MONDAY, "07:10"))
    second = make_appointment(
        marta,
        salon.bea,
        [salon.colour],
        at(TUESDAY, "09:00"),
        number="APT-2",
        notes="Allergic to ammonia",
    )
    Booking.objects.create(appointment=second, token_hash="2" * 64)
    clock.set(at(MONDAY, "07:20"))
    third = make_appointment(
        salon.lucia,
        salon.bea,
        [salon.cut],
        at(TUESDAY + dt.timedelta(days=1), "12:00"),
        number="APT-3",
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "16:00"),
        number="APT-COUNTER",
        source="counter",
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "17:00"),
        number="APT-WA",
        source="whatsapp",
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "18:00"),
        number="APT-GONE",
        deleted_at=at(MONDAY, "07:30"),
    )
    clock.set(at(MONDAY, "08:00"))
    return type(
        "Inbox", (), {"first": first, "second": second, "third": third, "marta": marta}
    )


def test_the_inbox_lists_the_online_bookings_the_newest_first(inbox):
    page = listed()
    assert numbers(page) == ["APT-3", "APT-2", "APT-1"]
    assert page["total"] == 3
    second = page["rows"][1]
    assert second["customer_name"] == "Marta Gil"
    assert second["customer_phone"] == "+34612345678"
    assert second["customer_email"] == "marta@example.com"
    assert second["service_names"] == "Colour"
    assert second["staff_name"] == "Bea Ruiz"
    assert second["notes"] == "Allergic to ammonia"
    assert second["total"] == 4500
    assert second["start"].isoformat() == "2030-03-05T09:00:00+01:00"
    assert [row["via_page"] for row in page["rows"]] == [False, True, True]


def test_the_inbox_searches_number_customer_phone_service_and_professional(inbox):
    assert numbers(listed({"search": "apt-2"})) == ["APT-2"]
    assert numbers(listed({"search": "lucia"})) == ["APT-3", "APT-1"]
    assert numbers(listed({"search": "612345678"})) == ["APT-2"]
    assert numbers(listed({"search": "colour"})) == ["APT-2"]
    assert numbers(listed({"search": "bea"})) == ["APT-3", "APT-2"]


def test_the_inbox_filters_by_column_status_day_and_professional(inbox):
    assert numbers(listed({"status": "pending"})) == ["APT-1"]
    assert numbers(
        listed({"date_from": TUESDAY.isoformat(), "date_to": TUESDAY.isoformat()})
    ) == ["APT-2", "APT-1"]
    assert numbers(listed({"staff_id": str(inbox.second.staff_id)})) == [
        "APT-3",
        "APT-2",
    ]
    assert numbers(listed({"customer_name": "marta"})) == ["APT-2"]
    assert numbers(listed({"service": "cut"})) == ["APT-3", "APT-1"]
    assert numbers(listed({"staff_name": "ana"})) == ["APT-1"]
    assert numbers(listed({"number": "3"})) == ["APT-3"]


def test_the_inbox_sorts_by_any_column_and_pages(inbox):
    assert numbers(listed({"sort": "start", "dir": "asc"})) == [
        "APT-2",
        "APT-1",
        "APT-3",
    ]
    assert numbers(listed({"sort": "number", "dir": "asc"})) == [
        "APT-1",
        "APT-2",
        "APT-3",
    ]
    page = listed({"sort": "number", "dir": "asc", "limit": 1, "offset": 1})
    assert (numbers(page), page["total"], page["limit"], page["offset"]) == (
        ["APT-2"],
        3,
        1,
        1,
    )


def test_the_employee_sees_the_online_bookings_of_her_own_agenda(inbox, salon):
    user = get_user_model().objects.create_user(username="bea", password="pw")
    salon.bea.user = ensure_hub_user(user)
    salon.bea.save()
    assert numbers(listed(role="hub_employee", actor=user)) == ["APT-3", "APT-2"]
    stranger = get_user_model().objects.create_user(username="nobody", password="pw")
    assert listed(role="hub_employee", actor=stranger)["total"] == 0


def test_the_inbox_needs_the_right_to_see_bookings(inbox):
    with pytest.raises(PermissionDenied):
        listed(permissions={"appointment.view_appointment"})


def test_one_booking_by_number_or_as_a_person_says_it(inbox):
    by_number = run("online_booking.booking.get", {"number": "apt-2"}).model_dump()
    assert by_number["id"] == inbox.second.id
    assert by_number["cancellation_reason"] == ""
    by_person = run(
        "online_booking.booking.get", {"customer": "Marta", "date": TUESDAY.isoformat()}
    )
    assert by_person.number == "APT-2"
    by_phone = run("online_booking.booking.get", {"customer": "612 345 678"})
    assert by_phone.number == "APT-2"
    # Without a day: her next online booking.
    assert run("online_booking.booking.get", {"customer": "Lucía"}).number == "APT-1"


def test_a_name_that_fits_several_bookings_says_which(inbox, salon):
    make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "12:00"), number="APT-4"
    )
    with pytest.raises(Conflict) as error:
        run(
            "online_booking.booking.get",
            {"customer": "Lucía", "date": TUESDAY.isoformat()},
        )
    assert error.value.code == "online_booking.booking_ambiguous"
    assert "APT-1" in error.value.message and "APT-4" in error.value.message
    # Without a day, two different customers whose names fit are ambiguous too.
    with pytest.raises(Conflict) as error:
        run("online_booking.booking.get", {"customer": "a"})
    assert error.value.code == "online_booking.booking_ambiguous"


def test_a_booking_that_is_not_online_is_not_found(inbox):
    for number in ("APT-COUNTER", "APT-WA", "APT-GONE", "APT-NONE"):
        with pytest.raises(NotFound) as error:
            run("online_booking.booking.get", {"number": number})
        assert error.value.code == "online_booking.booking_not_found"


def test_ties_go_by_id_in_the_lists_own_direction(salon):
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    rows = [
        make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, f"{hour:02}:00"), status="pending")
        for hour in range(9, 13)
    ]
    for row in rows:
        Booking.objects.create(appointment=row, token_hash=str(row.id).replace("-", "").ljust(64, "0"))
    by_id = sorted(row.id for row in rows)
    assert_reads_backwards(listed_with(run, "online_booking.booking.list", "status", by_dir=True), by_id)
