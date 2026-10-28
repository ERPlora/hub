"""The book's reads: the reservations of some days (or of the whole book, searching), one reservation by id
or as said, a day's figures and slots, the free tables, the slots, the blocked dates, the waitlist and
the rules. Each is a ``READ ONLY`` operation with its permission."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from .conftest import (
    THURSDAY,
    TODAY,
    TOMORROW,
    ctx_for,
    make_blocked,
    make_customer,
    make_entry,
    make_reservation,
    make_slot,
    make_table,
    make_zone,
    run,
    set_rules,
    set_week_hours,
)

pytestmark = pytest.mark.django_db

NOBODY = ctx_for(permissions=set())
#: Madrid's clocks go back an hour (03:00 summer time is 02:00 again) and forward (02:00 is 03:00).
CLOCKS_BACK = dt.date(2026, 10, 25)
CLOCKS_FORWARD = dt.date(2026, 3, 29)


def rows(result) -> list:
    return [row for row in result.rows]


# ── reservation.reservation.list ─────────────────────────────────────────────────────────────────


def test_the_list_gives_a_day_by_time_with_its_table_and_its_end():
    table = make_table("5", zone=make_zone("Terrace"))
    late = make_reservation(time="22:00", table=table, party_size=4)
    early = make_reservation(time="20:30", duration_minutes=90)
    make_reservation(date=TODAY, time="14:00")
    result = run(
        "reservation.reservation.list",
        {"date_from": "2026-10-15", "date_to": "2026-10-15"},
    )
    assert [row.id for row in result.rows] == [early.id, late.id]
    assert result.total == 2
    row = result.rows[1]
    assert (row.table_label, row.table_capacity, row.end_time) == (
        "5 (Terrace)",
        4,
        dt.time(0, 0),
    )
    assert (result.rows[0].table_label, result.rows[0].end_time) == ("", dt.time(22, 0))


def test_the_end_of_a_reservation_is_its_real_end_on_the_wall_clock_the_nights_the_clocks_change():
    back = make_reservation(date=CLOCKS_BACK, time="01:37", duration_minutes=90)
    forward = make_reservation(date=CLOCKS_FORWARD, time="01:30", duration_minutes=90)
    # 90 real minutes: 02:07 of the second pass in October, 04:00 summer time in March.
    assert run("reservation.reservation.get", {"id": str(back.id)}).end_time == dt.time(2, 7)
    assert run("reservation.reservation.get", {"id": str(forward.id)}).end_time == dt.time(4, 0)

def test_the_list_hides_the_deleted_and_filters_by_status_table_customer_party_and_time():
    table = make_table("5")
    card = make_customer("Marta")
    make_reservation(
        time="20:00", status="confirmed", table=table, party_size=2, customer_id=card.id
    )
    make_reservation(time="21:00", status="cancelled", party_size=6)
    make_reservation(time="21:30", is_deleted=True)

    def times(**filters):
        return [
            f"{row.time:%H:%M}"
            for row in run("reservation.reservation.list", filters).rows
        ]

    assert times() == ["20:00", "21:00"]
    assert times(status="cancelled") == ["21:00"]
    assert times(table_id=str(table.id)) == ["20:00"]
    assert times(customer_id=str(card.id)) == ["20:00"]
    assert times(party_size_from=3) == ["21:00"]
    assert times(party_size_to=3) == ["20:00"]
    assert times(time="21") == ["21:00"]


def test_searching_looks_through_the_whole_book_by_name_phone_however_typed_or_email():
    make_reservation(guest_name="Ana García", guest_phone="+34600111222")
    make_reservation(
        date=TOMORROW + dt.timedelta(days=7),
        guest_name="Luis",
        guest_email="luis@bar.es",
    )
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "garcía"}).rows
    ] == ["Ana García"]
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "600 111 222"}).rows
    ] == ["Ana García"]
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "bar.es"}).rows
    ] == ["Luis"]


def test_the_list_sorts_in_calendar_order_and_pages():
    for day, at in ((TOMORROW, "22:00"), (TODAY, "21:00"), (TOMORROW, "13:00")):
        make_reservation(date=day, time=at)
    result = run("reservation.reservation.list", {"limit": 2})
    assert [(row.date, f"{row.time:%H:%M}") for row in result.rows] == [
        (TODAY, "21:00"),
        (TOMORROW, "13:00"),
    ]
    assert (result.total, result.limit, result.offset) == (3, 2, 0)
    backwards = run("reservation.reservation.list", {"sort": "-starts_at", "limit": 1})
    assert [(row.date, f"{row.time:%H:%M}") for row in backwards.rows] == [
        (TOMORROW, "22:00")
    ]


def test_an_erased_guest_comes_without_a_name():
    make_reservation(guest_name="")
    assert run("reservation.reservation.list").rows[0].guest_name == ""


# ── reservation.reservation.get ──────────────────────────────────────────────────────────────────


def test_a_reservation_is_read_by_id_or_by_its_guest_and_day():
    ana = make_reservation(guest_name="Ana García", guest_phone="+34600111222")
    make_reservation(date=TODAY, time="14:00", guest_name="Luis")
    assert run("reservation.reservation.get", {"id": str(ana.id)}).id == ana.id
    assert run("reservation.reservation.get", {"guest": "ana"}).id == ana.id
    assert (
        run(
            "reservation.reservation.get", {"guest": "600111222", "day": "2026-10-15"}
        ).id
        == ana.id
    )


def test_a_guest_with_several_reservations_must_say_which_day():
    make_reservation(guest_name="Ana")
    make_reservation(date=TOMORROW + dt.timedelta(days=1), guest_name="Ana")
    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.get", {"guest": "Ana"})
    assert caught.value.code == "reservation.reservation_ambiguous"
    assert "15/10" in caught.value.message or "2026-10-15" in caught.value.message


def test_a_missing_or_deleted_reservation_is_not_found():
    gone = make_reservation(is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"guest": "Nadie"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.reservation.get", ref)
        assert caught.value.code == "reservation.reservation_not_found"


def test_a_past_reservation_is_found_by_id_and_by_day_but_the_guest_alone_names_the_coming_ones():
    old = make_reservation(date=TODAY - dt.timedelta(days=3), guest_name="Ana")
    coming = make_reservation(guest_name="Ana")
    assert run("reservation.reservation.get", {"guest": "Ana"}).id == coming.id
    assert (
        run("reservation.reservation.get", {"guest": "Ana", "day": str(old.date)}).id
        == old.id
    )


# RESERVATION-F19 — a flow's template prints a value as it comes, with no clock nor formatter: the WhatsApp
# message that confirms a table says «el martes, 5 de marzo de 2030 a las 21:30» because the reservation gives
# its day and its hour ready to read, in the language of whoever asks (not the thread's), as Appointments does.
def test_a_reservation_gives_its_day_and_hour_ready_to_read_in_the_callers_language():
    booked = make_reservation(date=dt.date(2030, 3, 5), time="21:30", status="confirmed")
    spanish = run("reservation.reservation.get", {"id": str(booked.id)}, ctx_for(language="es"))
    assert (spanish.date_label, spanish.time_label) == ("martes, 5 de marzo de 2030", "21:30")
    english = run("reservation.reservation.get", {"id": str(booked.id)}, ctx_for(language="en"))
    assert (english.date_label, english.time_label) == ("Tuesday, March 5, 2030", "21:30")
    listed = run(
        "reservation.reservation.list", {"date_from": "2030-03-05"}, ctx_for(language="es")
    )
    assert (listed.rows[0].date_label, listed.rows[0].time_label) == (
        "martes, 5 de marzo de 2030",
        "21:30",
    )


def test_the_day_and_hour_ready_to_read_are_the_wall_clock_whatever_the_zone():
    """A reservation keeps the business's wall clock: a 23:30 table stays on its day and its hour, east or
    west of UTC."""
    late = make_reservation(date=dt.date(2030, 3, 5), time="23:30")
    for zone in ("Pacific/Auckland", "Pacific/Honolulu"):
        with timezone.override(zone):
            read = run("reservation.reservation.get", {"id": str(late.id)})
        assert (read.date_label, read.time_label) == ("Tuesday, March 5, 2030", "23:30")


# ── reservation.availability.day ─────────────────────────────────────────────────────────────────


def test_a_day_counts_its_slots_like_the_gate_and_adds_up_its_covers():
    lunch = make_slot(THURSDAY, "13:00", "16:00", max_reservations=3)
    dinner = make_slot(THURSDAY, "20:00", "23:30", max_reservations=2, max_covers=10)
    make_slot(THURSDAY + 1, "20:00", "23:30")
    make_reservation(time="13:30", party_size=2, status="confirmed")
    make_reservation(time="14:00", party_size=4, status="cancelled")
    make_reservation(time="20:00", party_size=6, status="seated")
    make_reservation(time="21:00", party_size=3, status="completed")
    make_reservation(time="21:30", party_size=5, status="no_show")
    make_reservation(time="22:00", party_size=8, is_deleted=True)
    make_reservation(date=TODAY, time="21:00", party_size=2)
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.date, day.today, day.timezone, day.closed) == (
        TOMORROW,
        TODAY,
        "Europe/Madrid",
        False,
    )
    loads = {slot.id: slot for slot in day.slots}
    assert [slot.id for slot in day.slots] == [lunch.id, dinner.id]
    assert (
        loads[lunch.id].reserved,
        loads[lunch.id].covers,
        loads[lunch.id].available,
        loads[lunch.id].full,
    ) == (
        1,
        2,
        2,
        False,
    )
    assert (
        loads[dinner.id].reserved,
        loads[dinner.id].covers,
        loads[dinner.id].available,
        loads[dinner.id].full,
    ) == (
        2,
        9,
        0,
        True,
    )
    assert (day.reservations, day.covers) == (3, 11)


def test_a_day_without_a_date_is_the_business_today():
    assert run("reservation.availability.day").date == TODAY


def test_a_day_says_its_blocks_and_whether_it_is_closed():
    make_blocked(
        reason="Private event",
        is_full_day=False,
        blocked_from=dt.time(20),
        blocked_until=dt.time(22),
    )
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.closed, [block.reason for block in day.blocks]) == (
        False,
        ["Private event"],
    )
    make_blocked(reason="Holiday", blocked_from=None)
    assert run("reservation.availability.day", {"date": "2026-10-15"}).closed is True


def test_a_day_brings_the_business_hours_and_marks_the_slots_that_start_closed():
    set_week_hours([("13:00", "16:00")])
    lunch = make_slot(THURSDAY, "13:00", "16:00")
    dinner = make_slot(THURSDAY, "20:00", "23:30")
    day = run(
        "reservation.availability.day", {"date": "2026-10-15"}, ctx_for("hub_employee")
    )
    assert day.hours_restricted is True
    assert [(span.start, span.end) for span in day.spans] == [
        (dt.datetime(2026, 10, 15, 13, 0), dt.datetime(2026, 10, 15, 16, 0))
    ]
    in_hours = {slot.id: slot.in_hours for slot in day.slots}
    assert in_hours == {lunch.id: True, dinner.id: False}


def test_the_default_week_nobody_confirmed_does_not_restrict():
    # Schedules ships Monday to Friday 09:00–18:00 until the business saves or confirms its week: a
    # restaurant that never opened Schedules must still book its dinners.
    make_slot(THURSDAY, "20:00", "23:30")
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.hours_restricted, day.spans, day.slots[0].in_hours) == (False, [], True)


# ── reservation.availability.tables ──────────────────────────────────────────────────────────────


def test_the_free_tables_are_the_ones_in_service_without_a_live_reservation_then():
    room = make_zone("Room")
    shut = make_zone("Closed room", is_active=False)
    two = make_table("2", zone=room, capacity=2)
    ten = make_table("10", zone=room, capacity=6)
    four = make_table("4", zone=room, capacity=4)
    make_table("6", zone=room, blocked=True)
    make_table("7", zone=room, is_active=False)
    make_table("8", zone=room, is_deleted=True)
    make_table("9", zone=shut)
    make_reservation(time="20:00", table=four, status="confirmed")
    make_reservation(time="21:00", table=ten, status="completed")
    make_reservation(time="21:00", table=two, status="cancelled")
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:00", "party_size": 3},
        ctx_for("hub_employee"),
    )
    shown = [(row.number, row.free, row.fits) for row in result.rows]
    assert shown == [("10", True, True), ("2", True, False), ("4", False, True)]
    taken = result.rows[2]
    assert (taken.taken_from, taken.taken_until, taken.label, taken.capacity) == (
        dt.time(20),
        dt.time(22),
        "4 (Room)",
        4,
    )


def test_the_free_tables_count_a_stay_in_real_time_the_nights_the_clocks_change():
    five = make_table("5")

    def table_at(day: dt.date, time: str):
        return run(
            "reservation.availability.tables",
            {"date": day.isoformat(), "time": time, "duration_minutes": 60},
        ).rows[0]

    # 01:37 summer time plus 90 real minutes ends at 02:07 of the second pass (winter time).
    make_reservation(
        date=CLOCKS_BACK, time="01:37", duration_minutes=90, table=five, status="confirmed"
    )
    assert table_at(CLOCKS_BACK, "03:00").free
    taken = table_at(CLOCKS_BACK, "02:30")
    assert (taken.free, taken.taken_from, taken.taken_until) == (
        False,
        dt.time(1, 37),
        dt.time(2, 7),
    )
    # 01:00 winter time plus 90 real minutes ends at 03:30 summer time.
    make_reservation(
        date=CLOCKS_FORWARD, time="01:00", duration_minutes=90, table=five, status="confirmed"
    )
    taken = table_at(CLOCKS_FORWARD, "03:00")
    assert (taken.free, taken.taken_until) == (False, dt.time(3, 30))
    assert table_at(CLOCKS_FORWARD, "03:30").free


def test_the_free_tables_look_around_the_business_day_not_the_utc_one_west_of_utc():
    """West of UTC an evening is already the next UTC day: the neighbours of a stay are the days of
    the business's wall clock, so a table kept since the night before is still found."""
    five = make_table("5")
    with timezone.override("America/New_York"):
        make_reservation(
            date=dt.date(2030, 3, 4),
            time="23:00",
            duration_minutes=24 * 60,
            table=five,
            status="confirmed",
        )
        row = run(
            "reservation.availability.tables",
            {"date": "2030-03-05", "time": "22:00", "duration_minutes": 60},
        ).rows[0]
    assert (row.free, row.taken_from, row.taken_until) == (False, dt.time(23, 0), dt.time(23, 0))


def test_a_reservation_being_changed_does_not_take_its_own_table():
    four = make_table("4")
    mine = make_reservation(time="21:00", table=four, status="confirmed")
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:30", "exclude_id": str(mine.id)},
    )
    assert [(row.number, row.free) for row in result.rows] == [("4", True)]


def test_the_free_tables_search_by_number_name_or_zone():
    make_table("1", zone=make_zone("Terrace"))
    make_table("2", zone=make_zone("Bar"))
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:00", "search": "terr"},
    )
    assert [row.number for row in result.rows] == ["1"]


# ── Slots, blocked dates, waitlist, settings ─────────────────────────────────────────────────────


def test_the_slots_list_by_weekday_and_start_without_the_deleted():
    dinner = make_slot(THURSDAY, "20:00", "23:30")
    lunch = make_slot(THURSDAY, "13:00", "16:00")
    monday = make_slot(0, "13:00", "16:00", max_covers=30)
    make_slot(1, "13:00", "16:00", is_deleted=True)
    assert [row.id for row in run("reservation.time_slot.list").rows] == [
        monday.id,
        lunch.id,
        dinner.id,
    ]
    assert [
        row.id
        for row in run("reservation.time_slot.list", {"day_of_week": THURSDAY}).rows
    ] == [
        lunch.id,
        dinner.id,
    ]
    assert (
        run("reservation.time_slot.list", {"day_of_week": 0}).rows[0].max_covers == 30
    )


def test_the_blocked_dates_list_by_date_without_the_deleted():
    later = make_blocked(TOMORROW + dt.timedelta(days=5), reason="Holiday")
    soon = make_blocked(
        TOMORROW,
        reason="Event",
        is_full_day=False,
        blocked_from=dt.time(20),
        blocked_until=dt.time(23),
    )
    make_blocked(TOMORROW + dt.timedelta(days=9), is_deleted=True)
    assert [row.id for row in run("reservation.blocked_date.list").rows] == [
        soon.id,
        later.id,
    ]
    assert [
        row.id
        for row in run("reservation.blocked_date.list", {"is_full_day": True}).rows
    ] == [later.id]
    assert [
        row.id
        for row in run("reservation.blocked_date.list", {"date_to": "2026-10-16"}).rows
    ] == [soon.id]


def test_the_waitlist_keeps_its_order_and_filters():
    first = make_entry(time="20:30", guest_name="Luis", guest_phone="+34600333444")
    second = make_entry(time="21:00", guest_name="Marta", is_contacted=True)
    converted = make_reservation()
    make_entry(time="21:00", guest_name="Pepa", reservation=converted)
    make_entry(guest_name="Gone", is_deleted=True)
    page = run("reservation.waitlist.list")
    assert [row.guest_name for row in page.rows] == ["Luis", "Marta", "Pepa"]
    assert (page.rows[2].is_converted, page.rows[2].reservation_id) == (
        True,
        converted.id,
    )
    assert [
        row.id for row in run("reservation.waitlist.list", {"is_contacted": True}).rows
    ] == [second.id]
    assert [
        row.guest_name
        for row in run("reservation.waitlist.list", {"is_converted": False}).rows
    ] == [
        "Luis",
        "Marta",
    ]
    assert [
        row.id for row in run("reservation.waitlist.list", {"search": "600 333"}).rows
    ] == [first.id]


def test_the_settings_are_the_factory_ones_until_saved_with_the_business_zone():
    settings = run("reservation.settings.get")
    assert (settings.require_phone, settings.max_party_size, settings.timezone) == (
        True,
        20,
        "Europe/Madrid",
    )
    set_rules(max_party_size=12, auto_confirm=True)
    settings = run("reservation.settings.get")
    assert (settings.max_party_size, settings.auto_confirm) == (12, True)


def test_every_read_needs_its_permission():
    for name, data in (
        ("reservation.reservation.list", {}),
        ("reservation.availability.day", {}),
        ("reservation.availability.tables", {"date": "2026-10-15", "time": "21:00"}),
        ("reservation.time_slot.list", {}),
        ("reservation.blocked_date.list", {}),
        ("reservation.waitlist.list", {}),
        ("reservation.settings.get", {}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, NOBODY)
