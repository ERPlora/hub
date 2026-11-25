"""What a customer may pick on the public page: the services booked online, who does them and the free times."""

import pytest
from live.errors import Conflict, OperationError

from apps.online_booking.queries.offer import public_services
from apps.online_booking.schemas import PublicServicesIn

from .conftest import (
    HUB_DB,
    MONDAY,
    TUESDAY,
    assign,
    at,
    make_appointment,
    make_day,
    make_member,
    make_page,
    make_rules,
    make_service,
    public,
    public_ctx,
)

pytestmark = HUB_DB


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
    cut = public_services(public_ctx(), PublicServicesIn(search="hair")).rows[0]
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
