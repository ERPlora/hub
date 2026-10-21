"""Read operations of the appointment app: the agenda, one appointment, its history, a customer's visits,
the counters, the agenda's lanes, the free times, a time's verdict, the blocks, the series and the settings.

Cases from the current product's tests (`list_for_customer`, `count_active_for_service`,
`bell_to_confirm`, `availability*`, `blocked_times_overlapping`, `upcoming_reads`) and its WORKFLOW.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.appointment.models import Appointment, History

from .conftest import (
    MONDAY,
    assign,
    at,
    make_appointment,
    make_block,
    make_customer,
    make_day,
    make_member,
    make_series,
    make_settings,
    make_shift,
    make_time_off,
    run,
    wall,
)

pytestmark = pytest.mark.django_db
TUESDAY = MONDAY + dt.timedelta(days=1)


def employee_linked_to(member, make_user):
    """An employee's context whose account is linked to ``member`` (their own agenda)."""
    from .conftest import ctx_for

    user = make_user("bea", role="hub_employee")
    member.user = user
    member.save(update_fields=["user"])
    return ctx_for("hub_employee", actor=user)


def as_ctx(ctx, name, data=None):
    from live.operations import get

    op = get(name)
    return op(ctx, op.input.model_validate(data or {}))


# The agenda


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


# One appointment and its history


def test_an_appointment_is_read_by_its_id_or_its_number_with_contact_and_notes(salon):
    appointment = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        number="APT-20261019-0007",
        internal_notes="7/1",
    )
    by_number = run("appointment.appointment.get", {"number": "APT-20261019-0007"})
    assert (by_number.id, by_number.customer_phone, by_number.internal_notes) == (
        appointment.id,
        "+34600111222",
        "7/1",
    )
    with pytest.raises(NotFound) as missing:
        run("appointment.appointment.get", {"number": "APT-NOPE"})
    assert missing.value.code == "appointment.appointment_not_found"


def test_an_employee_cannot_read_a_colleagues_appointment(salon, make_user):
    theirs = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    ctx = employee_linked_to(salon.bea, make_user)
    with pytest.raises(NotFound):
        as_ctx(ctx, "appointment.appointment.get", {"id": str(theirs.id)})


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


# A customer's visits (her card's block)


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


# gh:appointments#143, #146 · gh:hub#1662 — a model reading a stranger's message (a flow's step gets every
# read of the app) composes these reads: what is the salon's (its notes, a cancellation's reason) and the
# customer's contact never reach a caller that is not a person. The team, and its assistant with the person's
# own session, read them; the day's agenda carries neither, for anybody.
@pytest.mark.parametrize("actor", ["flow_run:0190a1b2", "system", None])
def test_a_caller_who_is_not_a_person_reads_a_visit_without_the_salons_notes_nor_the_contact(salon, actor):
    from apps.appointment.apps import AppointmentConfig

    booked = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        notes="Bring photo",
        internal_notes="7/1 + 6%",
        cancellation_reason="Allergy",
    )
    reads = {p for p in AppointmentConfig.permissions if p.split(".", 1)[-1].startswith("view")}
    automation = {"actor": actor, "permissions": reads}
    got = run("appointment.appointment.get", {"number": booked.number}, **automation)
    assert got.number == booked.number and got.customer_name == "Lucía Pérez"
    private = ("customer_phone", "customer_email", "notes", "internal_notes", "cancellation_reason")
    assert {name: getattr(got, name) for name in private} == dict.fromkeys(private, "")
    visits = run("appointment.appointment.list_for_customer", {"customer_id": str(salon.lucia.id)}, **automation)
    assert [(visit.id, visit.notes, visit.internal_notes) for visit in visits.rows] == [(booked.id, "", "")]
    person = run("appointment.appointment.get", {"number": booked.number})
    assert (person.customer_phone, person.internal_notes, person.cancellation_reason) == (
        "+34600111222",
        "7/1 + 6%",
        "Allergy",
    )
    agenda = run("appointment.appointment.list", {"date_from": MONDAY.isoformat()})
    assert not set(agenda.rows[0].model_dump()) & set(private)


# gh:appointments#151 — a flow's template prints a value as it comes, with no clock nor formatter: an
# automation confirming a booking says «el martes a las 10:30» because the appointment gives its day and its
# hour ready to read, in the language of whoever asks, on the business's clock (24 hours, as the old
# product's messages; the year kept: a booking can be months away).
def test_an_appointment_gives_its_day_and_hour_ready_to_read_in_the_callers_language(salon):
    tuesday = dt.date(2030, 3, 5)
    late = make_appointment(salon.lucia, salon.ana, [salon.cut], at(tuesday, "00:30"))
    spanish = run("appointment.appointment.get", {"id": str(late.id)}, language="es")
    assert (spanish.start_date_label, spanish.start_time_label) == ("martes, 5 de marzo de 2030", "00:30")
    english = run("appointment.appointment.get", {"id": str(late.id)}, language="en")
    assert (english.start_date_label, english.start_time_label) == ("Tuesday, March 5, 2030", "00:30")
    booked = run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": wall(MONDAY, "16:05"),
        },
        language="es",
    )
    assert booked.start_time_label == "16:05" and booked.start_date_label.startswith("lunes, ")


# Counters


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


# APPOINTMENT-G01 (old-hub:HUB_SHELL-F66) — what the hub tells the team as it happens: a booking or a
# cancellation the customer made herself (WhatsApp, the online booking), newest first, with what the notice says
# (who, which services, the day and the hour ready to say, with whom). One given or cancelled at the front desk is
# not told (who did it knows); an employee hears only her own agenda's; nothing older than the window.
def test_the_notices_are_the_customers_own_bookings_and_cancellations(salon, make_user):
    booked = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), source="whatsapp"
    )
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"))
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "12:00"),
        status="cancelled",
        cancelled_at=timezone.now(),
    )
    cancelled = make_appointment(
        make_customer("Pepa Gil"),
        salon.bea,
        [salon.colour],
        at(TUESDAY, "16:00"),
        source="online",
        status="cancelled",
        cancelled_by_customer=True,
        cancelled_at=timezone.now() + dt.timedelta(seconds=1),
    )
    page = run("appointment.appointment.notices", language="es")
    assert [(notice.kind, notice.id) for notice in page.rows] == [
        ("cancelled", cancelled.id),
        ("booked", cancelled.id),
        ("booked", booked.id),
    ]
    first = page.rows[0]
    assert (first.number, first.customer_name, first.service_names, first.staff_name) == (
        cancelled.number,
        "Pepa Gil",
        "Colour",
        "Bea Ruiz",
    )
    assert (first.start_time_label, first.start_date_label.split(",")[0]) == ("16:00", "martes")
    assert first.at == cancelled.cancelled_at
    own = employee_linked_to(salon.ana, make_user)
    assert [notice.id for notice in as_ctx(own, "appointment.appointment.notices").rows] == [booked.id]
    later = (timezone.now() + dt.timedelta(minutes=5)).isoformat()
    assert run("appointment.appointment.notices", {"since": later}).rows == []


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


# The agenda's lanes


def test_the_lanes_are_the_bookable_team_then_who_keeps_appointments_and_the_unassigned(
    salon,
):
    salon.bea.is_bookable = False
    salon.bea.save()
    carla = make_member("Carla", "Sanz", status="inactive")
    make_member("Dani", "Ortiz", status="on_leave")
    make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"))
    make_appointment(salon.lucia, carla, [salon.cut], at(MONDAY, "11:00"))
    make_appointment(salon.lucia, None, [salon.cut], at(MONDAY, "12:00"))
    lanes = run("appointment.agenda.lanes", {"date_from": MONDAY})
    assert [(lane.name, lane.takes_bookings) for lane in lanes.rows] == [
        ("Ana López", True),
        ("Bea Ruiz", False),
        ("Carla Sanz", False),
    ]
    assert (lanes.unassigned, lanes.sees_everyone) == (1, True)
    # Another day, nobody keeps a lane.
    assert [
        lane.name
        for lane in run("appointment.agenda.lanes", {"date_from": TUESDAY}).rows
    ] == ["Ana López"]


def test_an_employees_lanes_are_their_own(salon, make_user):
    ctx = employee_linked_to(salon.bea, make_user)
    lanes = as_ctx(ctx, "appointment.agenda.lanes", {"date_from": MONDAY})
    assert ([lane.staff_id for lane in lanes.rows], lanes.own_staff_id) == (
        [salon.bea.id],
        salon.bea.id,
    )


# Free times


def starts(out) -> list[str]:
    return [f"{slot.start:%H:%M}" for slot in out.slots]


def test_free_times_cross_the_business_hours_the_shift_the_blocks_and_the_appointments(
    salon,
):
    make_settings(slot_interval=30, allow_overlapping=False)
    make_day(0, ("09:00", "13:00"))
    make_shift(salon.ana, (0, "10:00", "14:00"))
    make_block(at(MONDAY, "11:00"), at(MONDAY, "11:30"), member=salon.ana)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"))
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Haircut"], "staff": "Ana"},
    )
    assert starts(out) == ["10:00", "10:30", "11:30", "12:30"]
    assert (out.duration_minutes, out.timezone) == (30, "Europe/Madrid")
    assert all(slot.staff_ids == [salon.ana.id] for slot in out.slots)


def test_free_times_take_the_professionals_own_length_and_ignore_the_appointment_being_moved(
    salon,
):
    make_settings(slot_interval=30, allow_overlapping=False)
    make_day(0, ("09:00", "11:00"))
    assign(salon.cut, salon.ana, duration=60)
    moving = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), duration=60
    )
    query = {"date": MONDAY, "services": ["Haircut"], "staff": "Ana"}
    assert starts(run("appointment.availability.slots", query)) == ["10:00"]
    assert starts(
        run("appointment.availability.slots", {**query, "exclude_id": str(moving.id)})
    ) == [
        "09:00",
        "09:30",
        "10:00",
    ]


def test_free_times_without_a_professional_say_who_is_free_among_those_who_do_the_service(
    salon,
):
    make_settings(slot_interval=60, allow_overlapping=False)
    make_day(0, ("09:00", "11:00"))
    assign(salon.colour, salon.ana)
    assign(salon.colour, salon.bea)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"))
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Colour"]},
    )
    assert [(f"{s.start:%H:%M}", sorted(s.staff_ids)) for s in out.slots] == [
        ("09:00", [salon.bea.id]),
        ("10:00", sorted([salon.ana.id, salon.bea.id])),
    ]


def test_a_service_nobody_is_assigned_to_is_offered_with_the_whole_bookable_team(salon):
    make_settings(slot_interval=60)
    make_day(0, ("09:00", "10:00"))
    salon.bea.is_bookable = False
    salon.bea.save()
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Haircut"]},
    )
    assert [s.staff_ids for s in out.slots] == [[salon.ana.id]]


def test_the_customer_is_offered_only_what_keeps_the_notice(salon):
    make_settings(
        min_booking_notice=24 * 60,
        slot_interval=60,
        calendar_start_hour=0,
        calendar_end_hour=24,
    )
    tomorrow = timezone.localdate() + dt.timedelta(days=1)
    make_day(tomorrow.weekday(), ("00:00", "00:00"))
    desk = run(
        "appointment.availability.slots", {"date": tomorrow, "duration_minutes": 60}
    )
    customer = run(
        "appointment.availability.slots",
        {"date": tomorrow, "duration_minutes": 60, "for_customer": True},
    )
    assert len(customer.slots) < len(desk.slots)
    assert all(not slot.within_notice for slot in customer.slots)
    assert any(slot.within_notice for slot in desk.slots)


# A time's verdict


@pytest.mark.parametrize(
    ("start", "code"),
    [
        ("10:00", None),
        ("08:30", "outside_schedule"),
        ("13:00", "outside_staff_hours"),
        ("11:00", "blocked"),
        ("12:00", "overlap"),
    ],
)
def test_a_time_is_answered_with_the_reason_it_cannot_be_booked(salon, start, code):
    make_settings(allow_overlapping=False)
    make_day(0, ("09:00", "14:00"))
    make_shift(salon.ana, (0, "09:00", "13:00"))
    make_block(at(MONDAY, "11:00"), at(MONDAY, "11:30"))
    make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), number="APT-OVER"
    )
    out = run(
        "appointment.availability.check",
        {
            "start": wall(MONDAY, start),
            "services": ["Haircut"],
            "staff": "Ana",
        },
    )
    assert (out.available, out.code) == (code is None, code)
    if code == "overlap":
        assert [c.number for c in out.conflicts] == ["APT-OVER"]
        assert "already has an appointment" in out.message
    if code is None:
        assert out.message == ""


def test_an_employee_hears_a_colleagues_time_is_taken_but_not_by_whom(salon, make_user):
    make_settings(allow_overlapping=False)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), number="APT-ANA")
    make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "12:00"), number="APT-BEA")
    ctx = employee_linked_to(salon.bea, make_user)
    asked = {"start": wall(MONDAY, "12:00"), "duration_minutes": 30}
    colleague = as_ctx(ctx, "appointment.availability.check", {**asked, "staff": "Ana"})
    assert (colleague.code, colleague.conflicts) == ("overlap", [])
    own = as_ctx(ctx, "appointment.availability.check", {**asked, "staff": "Bea"})
    assert [c.number for c in own.conflicts] == ["APT-BEA"]
    owner = run("appointment.availability.check", {**asked, "staff": "Ana"})
    assert [c.number for c in owner.conflicts] == ["APT-ANA"]


def test_approved_time_off_without_a_schedule_refuses_and_the_business_alone_ignores_people(
    salon,
):
    make_day(0, ("09:00", "14:00"))
    make_time_off(salon.ana, MONDAY)
    asked = {"start": wall(MONDAY, "10:00"), "duration_minutes": 30}
    assert (
        run("appointment.availability.check", {**asked, "staff": "Ana"}).code
        == "outside_staff_hours"
    )
    assert run("appointment.availability.check", asked).available is True


# Blocks, series and settings


def test_the_blocks_of_a_range_are_the_business_ones_and_the_professionals(salon):
    everyone = make_block(at(MONDAY, "08:00"), at(MONDAY, "09:00"), title="Meeting")
    ana_s = make_block(
        at(MONDAY, "10:00"), at(MONDAY, "11:00"), member=salon.ana, title="Doctor"
    )
    make_block(
        at(MONDAY, "12:00"), at(MONDAY, "13:00"), member=salon.bea, title="Dentist"
    )
    make_block(
        at(TUESDAY + dt.timedelta(days=1), "12:00"),
        at(TUESDAY + dt.timedelta(days=1), "13:00"),
    )
    page = run(
        "appointment.blocked_time.list",
        {"date_from": MONDAY, "staff_id": str(salon.ana.id)},
    )
    assert [b.id for b in page.rows] == [everyone.id, ana_s.id]
    assert page.rows[1].staff_name == "Ana López"
    assert (
        run(
            "appointment.blocked_time.list", {"date_from": MONDAY, "date_to": TUESDAY}
        ).total
        == 3
    )


def test_the_series_list_searches_and_filters(salon):
    weekly = make_series(salon)
    paused = make_series(salon, frequency="monthly", day_of_week=None, is_active=False)
    page = run("appointment.recurring.list", {"search": "haircut"})
    assert {r.id for r in page.rows} == {weekly.id, paused.id}
    assert [
        r.id for r in run("appointment.recurring.list", {"is_active": False}).rows
    ] == [paused.id]
    row = run("appointment.recurring.list", {"frequency": "weekly"}).rows[0]
    assert (row.service_names, row.day_of_week, row.time) == ("Haircut", 0, dt.time(10))


def test_a_series_says_its_next_date_and_how_many_booked_appointments_an_edit_reaches(
    salon,
):
    series = make_series(salon)
    for weeks, sale in (
        (0, None),
        (1, None),
        (2, "00000000-0000-7000-8000-000000000001"),
    ):
        day = MONDAY + dt.timedelta(weeks=weeks)
        make_appointment(
            salon.lucia,
            salon.ana,
            [salon.cut],
            at(day, "10:00"),
            recurring=series,
            occurrence_date=day,
            sale_id=sale,
        )
    detail = run(
        "appointment.recurring.get",
        {"id": str(series.id), "from_date": MONDAY + dt.timedelta(weeks=1)},
    )
    assert (detail.next_date, detail.upcoming, detail.charged) == (MONDAY, 2, 1)


def test_an_employee_reads_their_own_series_but_not_a_colleagues_nor_a_deleted_one(
    salon, make_user
):
    own = make_series(salon, staff=salon.bea)
    theirs = make_series(salon)
    gone = make_series(salon, staff=salon.bea)
    gone.deleted_at = timezone.now()
    gone.save()
    ctx = employee_linked_to(salon.bea, make_user)
    detail = as_ctx(ctx, "appointment.recurring.get", {"id": str(own.id)})
    assert (detail.id, detail.staff_id, detail.service_names) == (
        own.id,
        salon.bea.id,
        "Haircut",
    )
    for hidden in (theirs, gone):
        with pytest.raises(NotFound) as missing:
            as_ctx(ctx, "appointment.recurring.get", {"id": str(hidden.id)})
        assert missing.value.code == "appointment.recurring_not_found"


def test_the_settings_are_the_factory_ones_until_saved_with_the_business_zone():
    out = run("appointment.settings.get")
    assert (out.default_duration, out.allow_overlapping, out.timezone) == (
        60,
        True,
        "Europe/Madrid",
    )
    make_settings(slot_interval=20)
    assert run("appointment.settings.get").slot_interval == 20
    assert Appointment.objects.count() == 0
