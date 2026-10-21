"""Repeating appointments (APPOINTMENT-F12 to F15): creating a series books its window, booking again is
idempotent and skips what does not fit, editing «from this occurrence on» splits the series and moves,
cancels or leaves its appointments, and a series is paused, reactivated and deleted.

Cases from the current product's tests (`recurring_*`, `series_*`, `hub_batteries_series_bounded`,
`batch_and_series_links`) and its `workflow/periodicas.md`.
"""

import datetime as dt
import uuid

import pytest
from live.errors import Conflict
from live.models import OutboxEvent

from apps.appointment.models import Appointment, History, Recurring

from .conftest import (
    MONDAY,
    at,
    make_settings,
    make_special_day,
    make_time_off,
    run,
    wall,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


def create(salon, **extra) -> object:
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "frequency": "weekly",
        "day_of_week": 0,
        "start_date": MONDAY.isoformat(),
        "time": "10:00",
        **extra,
    }
    return run("appointment.recurring.create", data)


def occurrences(series_id) -> list[dt.date]:
    return list(
        Appointment.objects.filter(recurring_id=series_id, deleted_at__isnull=True)
        .order_by("occurrence_date")
        .values_list("occurrence_date", flat=True)
    )


def test_creating_a_series_books_its_window(salon):
    make_settings(max_advance_booking=30)
    out = create(salon)
    dates = occurrences(out.recurring.id)
    assert dates[0] == MONDAY and all((day - MONDAY).days % 7 == 0 for day in dates)
    assert out.booked == len(dates) and out.skipped == [] and out.next_from is None
    first = Appointment.objects.get(
        recurring_id=out.recurring.id, occurrence_date=MONDAY
    )
    assert (first.start, first.status, first.staff_id) == (
        at(MONDAY, "10:00"),
        "confirmed",
        salon.ana.id,
    )
    assert (
        out.recurring.service_names == "Haircut"
        and out.recurring.duration_minutes == 30
    )
    assert OutboxEvent.objects.filter(name="appointment.recurring.created").count() == 1
    assert OutboxEvent.objects.filter(
        name="appointment.appointment.created"
    ).count() == len(dates)


def test_a_series_with_a_number_of_appointments_books_that_many(salon):
    assert create(salon, max_occurrences=3).booked == 3


def test_booking_again_never_books_a_date_twice_nor_one_cancelled_by_hand(salon):
    out = create(salon, max_occurrences=3)
    second = Appointment.objects.get(
        recurring_id=out.recurring.id, occurrence_date=MONDAY + dt.timedelta(weeks=1)
    )
    run("appointment.appointment.cancel", {"id": str(second.id)})
    again = run("appointment.recurring.materialize", {"id": str(out.recurring.id)})
    assert (again.booked, again.already_booked) == (0, 3)


def test_a_date_that_does_not_fit_is_skipped_with_its_reason_and_the_rest_book(salon):
    make_special_day(MONDAY + dt.timedelta(weeks=1), "Holiday")
    make_time_off(salon.ana, MONDAY + dt.timedelta(weeks=2))
    out = create(salon, max_occurrences=4)
    assert out.booked == 2
    assert [(skip.occurrence_date, skip.code) for skip in out.skipped] == [
        (MONDAY + dt.timedelta(weeks=1), "outside_schedule"),
        (MONDAY + dt.timedelta(weeks=2), "outside_staff_hours"),
    ]
    assert all(skip.message for skip in out.skipped)


def test_a_window_bigger_than_fifty_dates_books_in_turns(salon):
    make_settings(max_advance_booking=120)
    out = create(salon, frequency="daily", day_of_week=None)
    assert out.booked == 50 and out.next_from is not None
    rest = run(
        "appointment.recurring.materialize",
        {
            "id": str(out.recurring.id),
            "from_date": out.next_from.isoformat(),
            "to_date": out.to.isoformat(),
        },
    )
    assert rest.booked > 0
    assert len(occurrences(out.recurring.id)) == 50 + rest.booked


def test_a_series_whose_next_date_is_beyond_the_window_books_nothing_and_says_when(
    salon,
):
    make_settings(max_advance_booking=5)
    out = create(salon)
    assert (out.booked, out.upcoming_date) == (0, MONDAY)


def test_a_paused_or_finished_series_does_not_book(salon):
    out = create(salon, max_occurrences=1)
    run("appointment.recurring.deactivate", {"id": str(out.recurring.id)})
    with pytest.raises(Conflict) as paused:
        run("appointment.recurring.materialize", {"id": str(out.recurring.id)})
    assert paused.value.code == "appointment.recurring_inactive"
    run("appointment.recurring.activate", {"id": str(out.recurring.id)})
    ended = create(
        salon,
        start_date=(MONDAY - dt.timedelta(weeks=8)).isoformat(),
        end_date=(MONDAY - dt.timedelta(weeks=7)).isoformat(),
    )
    with pytest.raises(Conflict) as finished:
        run("appointment.recurring.materialize", {"id": str(ended.recurring.id)})
    assert finished.value.code == "appointment.recurring_ended"


def test_the_professional_must_do_the_services_like_a_single_booking(salon):
    from .conftest import assign

    assign(salon.cut, salon.bea)
    with pytest.raises(Conflict) as refused:
        create(salon)
    assert refused.value.code == "appointment.staff_not_eligible"
    assert Recurring.objects.count() == 0


def test_editing_from_a_later_date_splits_the_series_and_moves_what_follows(salon):
    out = create(salon, max_occurrences=4)
    old = out.recurring
    cut = MONDAY + dt.timedelta(weeks=2)
    charged = Appointment.objects.get(
        recurring_id=old.id, occurrence_date=MONDAY + dt.timedelta(weeks=3)
    )
    charged.sale_id = uuid.uuid7()
    charged.save()
    edited = run(
        "appointment.recurring.update",
        {"id": str(old.id), "from_date": cut.isoformat(), "time": "12:00"},
    )
    new = edited.recurring
    assert new.id != old.id and new.split_from_id == old.id and new.start_date == cut
    assert Recurring.objects.get(pk=old.id).end_date == cut - dt.timedelta(days=1)
    assert (edited.moved, edited.locked, edited.cancelled) == (1, 1, 0)
    moved = Appointment.objects.get(occurrence_date=cut, recurring_id=new.id)
    assert moved.start == at(cut, "12:00")
    assert Appointment.objects.get(pk=charged.pk).start == at(
        MONDAY + dt.timedelta(weeks=3), "10:00"
    )
    # The budget of four is split: two before the cut, two after.
    assert new.max_occurrences == 2
    before = Appointment.objects.get(recurring_id=old.id, occurrence_date=MONDAY)
    assert before.start == at(MONDAY, "10:00")


def test_a_long_series_moves_every_appointment_and_each_says_who_had_it(salon):
    # gh:appointments#251 — handing a long series over moves all of its appointments, not the first fifty;
    # gh:appointments#253 — each one's history says from whom to whom, not just «rescheduled».
    make_settings(max_advance_booking=0)
    out = create(salon, frequency="daily", day_of_week=None)
    run("appointment.recurring.materialize", {"id": str(out.recurring.id)})
    booked = len(occurrences(out.recurring.id))
    assert booked > 50
    edited = run(
        "appointment.recurring.update",
        {"id": str(out.recurring.id), "from_date": MONDAY.isoformat(), "staff": "Bea"},
    )
    assert (edited.moved, edited.skipped) == (booked, [])
    handed = History.objects.filter(
        appointment__recurring_id=out.recurring.id, action="staff_changed"
    )
    assert handed.count() == booked
    assert {(line.old_value["staff"], line.new_value["staff"]) for line in handed} == {
        ("Ana López", "Bea Ruiz")
    }


def test_editing_from_the_first_date_edits_the_series_in_place(salon):
    out = create(salon, max_occurrences=2)
    edited = run(
        "appointment.recurring.update",
        {"id": str(out.recurring.id), "from_date": MONDAY.isoformat(), "staff": "Bea"},
    )
    assert (
        edited.recurring.id == out.recurring.id
        and edited.recurring.staff_name == "Bea Ruiz"
    )
    assert edited.moved == 2
    assert set(
        Appointment.objects.filter(recurring_id=out.recurring.id).values_list(
            "staff_id", flat=True
        )
    ) == {salon.bea.id}


def test_a_new_pattern_cancels_what_no_longer_falls_on_it_and_books_its_own_dates(
    salon,
):
    out = create(salon, max_occurrences=3)
    edited = run(
        "appointment.recurring.update",
        {
            "id": str(out.recurring.id),
            "from_date": MONDAY.isoformat(),
            "day_of_week": 2,
        },
    )
    assert edited.cancelled == 3 and edited.booked == 3
    wednesday = MONDAY + dt.timedelta(days=2)
    booked = Appointment.objects.filter(recurring_id=out.recurring.id, status="confirmed")
    assert sorted(booked.values_list("occurrence_date", flat=True)) == [
        wednesday + dt.timedelta(weeks=week) for week in range(3)
    ]
    # The Mondays are cancelled and no longer hold a date of the series (a pattern changed back books
    # them again).
    cancelled = Appointment.objects.filter(
        recurring_id=out.recurring.id, status="cancelled"
    )
    assert cancelled.count() == 3
    assert set(cancelled.values_list("occurrence_date", flat=True)) == {None}
    assert all(
        line.reason
        for item in cancelled
        for line in item.history.filter(action="cancelled")
    )


def test_a_series_is_paused_reactivated_and_deleted_and_keeps_its_booked_appointments(
    salon,
):
    out = create(salon, max_occurrences=2)
    series = str(out.recurring.id)
    assert run("appointment.recurring.deactivate", {"id": series}).is_active is False
    assert run("appointment.recurring.activate", {"id": series}).is_active is True
    run("appointment.recurring.delete", {"id": series})
    assert Recurring.objects.get(pk=series).deleted_at is not None
    assert len(occurrences(series)) == 2
    assert run("appointment.recurring.list").total == 0
    assert OutboxEvent.objects.filter(name="appointment.recurring.deleted").count() == 1


def test_a_series_wall_clock_time_survives_the_change_of_time(salon):
    make_settings(max_advance_booking=0)
    autumn = dt.date(2026, 10, 19)
    if autumn < MONDAY:
        autumn = MONDAY
    out = create(salon, start_date=autumn.isoformat(), max_occurrences=3)
    for item in Appointment.objects.filter(recurring_id=out.recurring.id):
        assert wall(item.occurrence_date, "10:00")[-5:] == item.start.astimezone(
            at(MONDAY, "10:00").tzinfo
        ).strftime("%H:%M")


# ── Editing keeps a pause; only a series that lost its professional comes back with a new one ───


def test_editing_a_paused_series_keeps_it_paused_and_books_nothing(salon):
    make_settings(max_advance_booking=30)
    out = create(salon)
    series = str(out.recurring.id)
    run("appointment.recurring.deactivate", {"id": series})
    in_place = run(
        "appointment.recurring.update",
        {"id": series, "from_date": MONDAY.isoformat(), "day_of_week": 2},
    )
    assert (in_place.recurring.is_active, in_place.booked) == (False, 0)
    later = MONDAY + dt.timedelta(weeks=2)
    split = run(
        "appointment.recurring.update",
        {"id": series, "from_date": later.isoformat(), "time": "12:00"},
    )
    assert split.recurring.id != out.recurring.id
    assert (split.recurring.is_active, split.booked) == (False, 0)


def test_editing_a_series_of_an_erased_customer_keeps_it_paused(salon):
    from apps.appointment import events

    from .conftest import A

    make_settings(max_advance_booking=30)
    out = create(salon, max_occurrences=2)
    series = str(out.recurring.id)
    events.react(A, "customer.customer.erased", {"id": str(salon.lucia.id)})
    edited = run(
        "appointment.recurring.update",
        {"id": series, "from_date": MONDAY.isoformat(), "time": "12:00", "max_occurrences": 4},
    )
    assert (edited.recurring.is_active, edited.booked) == (False, 0)


def test_a_series_that_lost_its_professional_comes_back_when_it_gets_one(salon):
    from apps.appointment import events

    from .conftest import A

    make_settings(max_advance_booking=30)
    out = create(salon, max_occurrences=2)
    series = str(out.recurring.id)
    events.react(A, "staff.member.terminated", {"id": str(salon.ana.id)})
    assert Recurring.objects.get(pk=series).is_active is False
    edited = run(
        "appointment.recurring.update",
        {"id": series, "from_date": MONDAY.isoformat(), "staff": "Bea"},
    )
    assert edited.recurring.is_active is True


# ── A pattern changed and changed back books its dates again ───────────────────────────────────


def test_changing_the_pattern_and_back_books_the_first_dates_again(salon):
    out = create(salon, max_occurrences=3)
    series = str(out.recurring.id)
    there = run(
        "appointment.recurring.update",
        {"id": series, "from_date": MONDAY.isoformat(), "day_of_week": 2},
    )
    assert (there.cancelled, there.booked) == (3, 3)
    back = run(
        "appointment.recurring.update",
        {"id": series, "from_date": MONDAY.isoformat(), "day_of_week": 0},
    )
    assert (back.cancelled, back.booked) == (3, 3)
    live = Appointment.objects.filter(recurring_id=series, status="confirmed").order_by("start")
    assert [item.occurrence_date for item in live] == [MONDAY + dt.timedelta(weeks=week) for week in range(3)]


@pytest.mark.parametrize("weeks", [1, -1])
def test_a_last_date_before_the_change_or_the_series_start_is_refused_on_its_field(salon, weeks):
    from live.errors import InvalidPayload

    out = create(salon, start_date=(MONDAY + dt.timedelta(weeks=1)).isoformat(), max_occurrences=3)
    # From a later date (a split): the last date before that date. From before it starts (in place):
    # the last date before the series' own first date.
    from_date = MONDAY + dt.timedelta(weeks=2 if weeks == 1 else 0)
    with pytest.raises(InvalidPayload) as refused:
        run(
            "appointment.recurring.update",
            {"id": str(out.recurring.id), "from_date": from_date.isoformat(), "end_date": (from_date - dt.timedelta(days=1)).isoformat()},
        )
    assert "end_date" in refused.value.fields
    assert Recurring.objects.count() == 1
