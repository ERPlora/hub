"""The online booking app's reads: the inbox over the diary's online appointments, the settings, and what the
public page reads (its texts, the services booked online, the free times and a booking by its link).

The inbox is the diary's appointments with ``source = "online"``: who sees what is the diary's rule (the
employee, her own agenda). The public reads answer only while the page is on, and only with what Services
lets the customer see.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from live.errors import Conflict, NotFound, OperationError, PermissionDenied

from apps.online_booking.models import Booking
from apps.online_booking.queries import hash_token, visitor_key
from base.services import ensure_hub_user

from .conftest import (
    MONDAY,
    TUESDAY,
    at,
    ctx_for,
    make_appointment,
    make_customer,
    make_day,
    make_member,
    make_page,
    make_rules,
    make_service,
    assign,
    public,
    public_ctx,
    run,
)

pytestmark = pytest.mark.django_db


def listed(data: dict | None = None, **ctx) -> dict:
    return run("online_booking.booking.list", data, **ctx).model_dump()


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


# ── The inbox ──────────────────────────────────────────────────────────────────────────────────


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


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


def test_the_settings_are_the_factory_ones_until_saved_with_the_rules_of_the_diary(db):
    settings = run("online_booking.settings.get").model_dump()
    assert settings == {
        "is_enabled": False,
        "page_title": "",
        "welcome_message": "",
        "primary_color": "#6366f1",
        "logo_url": "",
        "require_email": False,
        "max_upcoming_per_customer": 3,
        "allow_staff_selection": True,
        "allow_notes": True,
        "confirmation_message": "",
        "cancellation_policy": "",
        "min_booking_notice": 60,
        "max_advance_booking": 90,
        "slot_interval": 15,
        "auto_confirm_online": True,
        "allow_customer_cancellation": True,
        "cancellation_notice_hours": 24,
        "timezone": "Europe/Madrid",
    }


def test_the_employee_reads_the_settings_too(db):
    make_page(page_title="Salón Lucía")
    assert (
        run("online_booking.settings.get", role="hub_employee").page_title
        == "Salón Lucía"
    )


# ── The public page ────────────────────────────────────────────────────────────────────────────


def test_the_page_answers_nothing_while_it_is_off(salon):
    make_page(is_enabled=False)
    for name, data in (
        ("page", {}),
        ("services", {}),
        ("slots", {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()}),
    ):
        with pytest.raises(NotFound) as error:
            public(name, data)
        assert error.value.code == "online_booking.page_disabled", name


def test_the_page_reads_its_texts_in_the_visitors_language_and_the_rules(salon):
    make_rules(
        min_booking_notice=120, max_advance_booking=30, cancellation_notice_hours=48
    )
    page = public("page").model_dump()
    assert page["title"] == "Book an appointment"
    assert (
        page["min_booking_notice"],
        page["max_advance_booking"],
        page["cancellation_notice_hours"],
    ) == (120, 30, 48)
    assert page["allow_customer_cancellation"] is True
    assert page["timezone"] == "Europe/Madrid"
    make_page(
        page_title="Salón Lucía", welcome_message="¡Hola!", primary_color="#112233"
    )
    page = public("page")
    assert (page.title, page.welcome_message, page.primary_color) == (
        "Salón Lucía",
        "¡Hola!",
        "#112233",
    )


def test_the_public_reads_need_the_public_permission(salon):
    with pytest.raises(PermissionDenied):
        run("online_booking.public.page", ctx=ctx_for(role="hub_manager"))


def test_the_page_offers_the_services_booked_online_with_who_does_them(salon):
    make_service("Shave", allow_online_booking=False)
    make_service("Old perm", is_active=False)
    make_service("Consultation", is_bookable=False)
    page = public("services").model_dump()
    assert [row["name"] for row in page["rows"]] == ["Colour", "Haircut"]
    cut = page["rows"][1]
    assert (cut["price"], cut["duration_minutes"]) == (2000, 30)
    assert [person["name"] for person in cut["professionals"]] == [
        "Ana López",
        "Bea Ruiz",
    ]
    assert [row.name for row in public("services", {"search": "hair"}).rows] == [
        "Haircut"
    ]


def test_the_page_hides_prices_durations_and_professionals_when_the_business_does(
    salon,
):
    from apps.service.models import ServiceSettings

    ServiceSettings.objects.create(show_prices=False, show_duration=False)
    make_page(allow_staff_selection=False)
    cut = public("services", {"search": "hair"}).rows[0]
    assert (cut.price, cut.duration_minutes, cut.professionals) == (None, None, [])


def test_the_free_times_are_the_diarys_for_the_customer(salon):
    make_rules(slot_interval=30, min_booking_notice=0)
    make_day(1, ("09:00", "11:00"))
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "09:30"))
    answer = public(
        "slots",
        {
            "service_ids": [str(salon.cut.id)],
            "date": TUESDAY.isoformat(),
            "staff_id": str(salon.ana.id),
        },
    ).model_dump()
    assert answer["timezone"] == "Europe/Madrid"
    assert answer["duration_minutes"] == 30
    assert [slot["start"].strftime("%H:%M") for slot in answer["slots"]] == [
        "09:00",
        "10:00",
        "10:30",
    ]
    assert [person["name"] for person in answer["slots"][0]["professionals"]] == [
        "Ana López"
    ]


def test_without_a_professional_each_time_says_who_is_free(salon):
    make_rules(slot_interval=60, min_booking_notice=0)
    make_day(1, ("09:00", "11:00"))
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "09:00"))
    answer = public(
        "slots", {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()}
    )
    assert [
        (slot.start.strftime("%H:%M"), [person.name for person in slot.professionals])
        for slot in answer.slots
    ] == [("09:00", ["Bea Ruiz"]), ("10:00", ["Ana López", "Bea Ruiz"])]


def test_the_free_times_keep_the_minimum_notice(salon, clock):
    make_rules(slot_interval=60, min_booking_notice=120)
    make_day(0, ("08:00", "12:00"))
    clock.set(at(MONDAY, "08:30"))
    answer = public(
        "slots", {"service_ids": [str(salon.cut.id)], "date": MONDAY.isoformat()}
    )
    assert [slot.start.strftime("%H:%M") for slot in answer.slots] == ["11:00"]


def test_the_free_times_refuse_a_service_not_booked_online_and_a_chosen_professional_when_not_allowed(
    salon,
):
    shave = make_service("Shave", allow_online_booking=False)
    with pytest.raises(Conflict) as error:
        public("slots", {"service_ids": [str(shave.id)], "date": TUESDAY.isoformat()})
    assert error.value.code == "online_booking.service_not_online"
    make_page(allow_staff_selection=False)
    with pytest.raises(OperationError) as error:
        public(
            "slots",
            {
                "service_ids": [str(salon.cut.id)],
                "date": TUESDAY.isoformat(),
                "staff_id": str(salon.ana.id),
            },
        )
    assert error.value.code == "online_booking.staff_choice_disabled"
    assert error.value.fields == {"staff_id": error.value.message}


def test_a_professional_who_does_not_do_the_service_has_no_times(salon):
    other = make_member("Carla", "Sanz")
    shave = make_service("Beard trim")
    assign(shave, other)
    with pytest.raises(Conflict) as error:
        public(
            "slots",
            {
                "service_ids": [str(shave.id)],
                "date": TUESDAY.isoformat(),
                "staff_id": str(salon.ana.id),
            },
        )
    assert error.value.code == "appointment.staff_not_eligible"


# ── A booking by its link ──────────────────────────────────────────────────────────────────────


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
    seen = public("booking", {"token": "t" * 43})
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


# ── Helpers the services share ─────────────────────────────────────────────────────────────────


def test_the_visitor_is_a_fingerprint_of_the_address_the_load_balancer_adds():
    behind = public_ctx(ip="10.0.0.1")
    behind.request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.1, 203.0.113.9"
    direct = public_ctx(ip="203.0.113.9")
    assert visitor_key(behind) == visitor_key(direct)
    assert len(visitor_key(direct)) == 64
    assert "203.0.113.9" not in visitor_key(direct)
    assert visitor_key(public_ctx(ip="203.0.113.10")) != visitor_key(direct)


def test_a_link_is_kept_as_its_hash():
    assert hash_token("t" * 43) == hash_token("t" * 43)
    assert len(hash_token("t" * 43)) == 64
    assert hash_token("t" * 43) != "t" * 43
