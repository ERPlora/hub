"""The appointments as the agenda lists them, one's history, a customer's visits and the counters."""

import datetime as dt

import pytest
from django.utils import timezone

from apps.appointment.models import History
from apps.appointment.queries.appointments import APPOINTMENT_ORDER
from base.tests.actors import who_did_it
from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import (
    HUB_DB,
    MONDAY,
    TESTER,
    TUESDAY,
    as_ctx,
    at,
    employee_linked_to,
    make_appointment,
    make_customer,
    make_series,
    run,
)

pytestmark = HUB_DB


def test_every_column_the_agenda_sorts_by_reads_both_ways(salon):
    zoe = make_customer("Zoe Gil")
    early = make_appointment(zoe, salon.ana, [salon.cut], at(MONDAY, "09:00"), number="APT-X-0002")
    late = make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"), number="APT-X-0001", status="pending"
    )

    def listed(sort):
        return [row.id for row in run("appointment.appointment.list", {"date_from": MONDAY, "sort": sort}).rows]

    first = {"start": early, "number": late, "customer_name": late, "staff_name": early, "status": early}
    assert {column: listed(column)[0] for column in APPOINTMENT_ORDER} == {name: row.id for name, row in first.items()}
    assert [listed(f"-{column}") for column in APPOINTMENT_ORDER] == [listed(column)[::-1] for column in APPOINTMENT_ORDER]


def test_the_agenda_lists_a_days_appointments_in_order_on_the_business_clock(salon):
    late = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"))
    early = make_appointment(
        salon.lucia, salon.bea, [salon.cut, salon.colour], at(MONDAY, "09:00")
    )
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "09:00"))
    page = run("appointment.appointment.list", {"date_from": MONDAY})
    assert [row.id for row in page.rows] == [early.id, late.id]
    assert page.total == 2 and page.timezone == "Europe/Madrid"
    first = page.rows[0]
    assert first.start.utcoffset() == at(MONDAY, "09:00").utcoffset()
    assert (first.service_names, first.total, first.duration_minutes) == (
        "Haircut, Colour",
        6500,
        90,
    )
    assert [line.name for line in first.services] == ["Haircut", "Colour"]
    # A week at once.
    assert (
        run(
            "appointment.appointment.list", {"date_from": MONDAY, "date_to": TUESDAY}
        ).total
        == 3
    )


def test_the_agenda_filters_by_professional_status_customer_and_search(salon):
    pepa = make_customer("Pepa Gil")
    one = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), number="APT-X-0001"
    )
    two = make_appointment(
        pepa, salon.bea, [salon.colour], at(MONDAY, "10:00"), status="pending"
    )
    query = {"date_from": MONDAY}
    assert [
        r.id
        for r in run("appointment.appointment.list", {**query, "staff": "Bea"}).rows
    ] == [two.id]
    assert [
        r.id
        for r in run(
            "appointment.appointment.list", {**query, "status": "pending"}
        ).rows
    ] == [two.id]
    assert [
        r.id
        for r in run(
            "appointment.appointment.list", {**query, "customer_id": str(pepa.id)}
        ).rows
    ] == [two.id]
    for text, found in (("x-0001", one), ("pepa", two), ("colour", two)):
        assert [
            r.id
            for r in run("appointment.appointment.list", {**query, "search": text}).rows
        ] == [found.id], text
    by_staff = run(
        "appointment.appointment.list", {**query, "sort": "-staff_name"}
    ).rows
    assert [r.staff_name for r in by_staff] == ["Bea Ruiz", "Ana López"]


def test_the_agenda_pages_by_at_most_a_hundred_and_hides_deleted_ones(salon):
    for hour in range(9, 14):
        make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, f"{hour:02d}:00")
        )
    gone = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"))
    gone.deleted_at = timezone.now()
    gone.save()
    page = run(
        "appointment.appointment.list", {"date_from": MONDAY, "limit": 2, "offset": 2}
    )
    assert (page.total, len(page.rows), page.limit, page.offset) == (5, 2, 2, 2)


def test_an_employee_sees_only_their_own_agenda(salon, make_user):
    own = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "09:00"))
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    ctx = employee_linked_to(salon.bea, make_user)
    assert [
        r.id
        for r in as_ctx(ctx, "appointment.appointment.list", {"date_from": MONDAY}).rows
    ] == [own.id]


def test_an_employee_without_a_linked_record_sees_nothing(salon, make_user):
    from .conftest import ctx_for

    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    ctx = ctx_for("hub_employee", actor=make_user("nobody", role="hub_employee"))
    assert as_ctx(ctx, "appointment.appointment.list", {"date_from": MONDAY}).total == 0
    lanes = as_ctx(ctx, "appointment.agenda.lanes", {"date_from": MONDAY})
    assert (lanes.rows, lanes.own_staff_id, lanes.sees_everyone) == ([], None, False)


def test_the_history_lists_every_change_in_order(salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")
    )
    History.objects.create(appointment=appointment, action="created", actor="Ana")
    History.objects.create(
        appointment=appointment,
        action="cancelled",
        actor="",
        by_customer=True,
        reason="Ill",
    )
    page = run("appointment.appointment.history", {"id": str(appointment.id)})
    assert [(h.action, h.by_customer, h.reason) for h in page.rows] == [
        ("created", False, ""),
        ("cancelled", True, "Ill"),
    ]


@pytest.mark.parametrize("caller, who, by_platform", who_did_it(TESTER, "tester"))
def test_the_history_says_whether_a_person_or_the_platform_did_it(salon, caller, who, by_platform):
    """A person and an API key are named; the platform's own marks are kept, and the line says the platform did it."""
    pending = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="pending")
    run("appointment.appointment.confirm", {"id": str(pending.id)}, actor=caller)

    page = run("appointment.appointment.history", {"id": str(pending.id)})

    assert [(h.action, h.actor, h.by_platform) for h in page.rows] == [("confirmed", who, by_platform)]


def test_a_customers_visits_come_newest_first_with_their_notes(salon):
    old = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), notes="Bring photo"
    )
    new = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.colour],
        at(TUESDAY, "10:00"),
        internal_notes="7/1",
    )
    make_appointment(
        make_customer("Pepa Gil"), salon.ana, [salon.cut], at(MONDAY, "12:00")
    )
    page = run("appointment.appointment.list_for_customer", {"customer": "Lucía Pérez"})
    assert [r.id for r in page.rows] == [new.id, old.id]
    assert (page.rows[0].internal_notes, page.rows[1].notes) == ("7/1", "Bring photo")
    assert (
        run(
            "appointment.appointment.list_for_customer",
            {"customer_id": str(salon.lucia.id), "limit": 1},
        ).total
        == 2
    )


def test_the_upcoming_live_appointments_of_a_service_are_counted_with_the_first_one(
    salon,
):
    first = make_appointment(
        salon.lucia, salon.ana, [salon.colour], at(MONDAY, "10:00")
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut, salon.colour],
        at(TUESDAY, "10:00"),
        status="pending",
    )
    make_appointment(
        salon.lucia, salon.ana, [salon.colour], at(TUESDAY, "12:00"), status="cancelled"
    )
    make_appointment(
        salon.lucia, salon.ana, [salon.colour], timezone.now() - dt.timedelta(days=1)
    )
    count = run(
        "appointment.appointment.count_active_for_service", {"service": "Colour"}
    )
    assert (count.count, count.earliest) == (2, first.start)
    assert (
        run(
            "appointment.appointment.count_active_for_service",
            {"service_id": str(salon.cut.id)},
        ).count
        == 1
    )


def test_the_customers_own_bookings_waiting_for_confirmation_are_counted(salon):
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        status="pending",
        source="whatsapp",
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "11:00"),
        status="confirmed",
        source="online",
    )
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        timezone.now() - dt.timedelta(hours=2),
        status="pending",
        source="online",
    )
    # Two confirmed bookings ahead: a count of the confirmed ones instead would say 2, never 1.
    make_appointment(salon.lucia, salon.bea, [salon.colour], at(TUESDAY, "12:00"), status="confirmed", source="online")
    counted = run("appointment.appointment.count_to_confirm")
    assert (counted.count, counted.earliest) == (1, at(MONDAY, "10:00"))



def test_every_booking_to_confirm_is_listed_whatever_its_day_as_many_as_counted(salon):
    """hub#2640: «N to confirm» counted a booking of another day that the agenda's day never showed."""
    first = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="pending", source="online")
    later = make_appointment(
        salon.lucia, salon.bea, [salon.colour], at(MONDAY + dt.timedelta(days=15), "12:00"), status="pending"
    )
    next_day = make_appointment(salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "09:00"), status="pending")
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "11:00"), status="confirmed", source="online")
    make_appointment(salon.lucia, salon.ana, [salon.cut], timezone.now() - dt.timedelta(hours=2), status="pending")

    listed = run("appointment.appointment.list_to_confirm")

    assert [row.id for row in listed.rows] == [first.id, next_day.id, later.id]
    assert listed.total == run("appointment.appointment.count_to_confirm").count == 3


def test_an_employee_lists_and_counts_only_her_own_bookings_to_confirm(salon, make_user):
    own = make_appointment(salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "09:00"), status="pending")
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="pending")
    ctx = employee_linked_to(salon.bea, make_user)

    listed = as_ctx(ctx, "appointment.appointment.list_to_confirm")

    assert [row.id for row in listed.rows] == [own.id]
    assert listed.total == as_ctx(ctx, "appointment.appointment.count_to_confirm").count == 1


def test_a_confirmed_booking_leaves_the_list_to_confirm(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "09:00"), status="pending")
    run("appointment.appointment.confirm", {"id": str(booked.id)})
    assert run("appointment.appointment.list_to_confirm").rows == []

def _tied_appointments(salon):
    rows = [make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, f"{hour:02}:00")) for hour in range(9, 13)]
    return [row.id for row in rows], {"date_from": MONDAY}


def _tied_series(salon):
    return [make_series(salon).id for _ in range(4)], {}


@pytest.mark.parametrize(
    ("operation", "tied", "column"),
    [
        ("appointment.appointment.list", _tied_appointments, "status"),
        ("appointment.recurring.list", _tied_series, "time"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(salon, operation, tied, column):
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    ids, filters = tied(salon)
    assert_reads_backwards(listed_with(run, operation, column, **filters), sorted(ids))
