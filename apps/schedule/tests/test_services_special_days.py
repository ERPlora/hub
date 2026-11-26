"""Special days (SCHEDULE-F04, F06, F07, F13): one per date, created one by one or in bulk, corrected and deleted;
two at the same instant on the same date keep one."""

import datetime as dt

import pytest
from live.errors import Conflict, InvalidPayload, NotFound

from apps.schedule.models import SpecialDay, SpecialDayInterval
from apps.schedule.schemas.special_days import BulkSpecialDayIn, SpecialDayIn, SpecialDayPatchIn, SpecialDayRefIn

from apps.staff.tests.conftest import _race

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, make_special_day
from .test_services import hours, names, outbox, run, t

pytestmark = HUB_DB


def test_a_special_day_with_a_split_shift_is_one_day_and_two_intervals():
    eve = run(
        "schedule.special_day.create",
        SpecialDayIn(
            date="2026-12-24",
            name="Christmas Eve",
            is_closed=False,
            intervals=hours(("17:00", "19:00"), ("10:00", "13:00")),
            recurring_yearly=True,
            notes="half day",
        ),
    )
    row = SpecialDay.objects.get(pk=eve.id)
    assert (row.name, row.is_closed, row.recurring_yearly, row.notes) == (
        "Christmas Eve",
        False,
        True,
        "half day",
    )
    assert [(i.position, i.open_time) for i in row.intervals.order_by("position")] == [
        (0, t("10:00")),
        (1, t("17:00")),
    ]
    assert outbox() == [
        ("schedule.special_day.created", A.key, {"id": str(eve.id), "date": "2026-12-24"})
    ]


def test_a_closed_special_day_keeps_no_interval():
    christmas = run(
        "schedule.special_day.create", SpecialDayIn(date="2026-12-25", name="Christmas")
    )
    assert (
        christmas.is_closed
        and not SpecialDayInterval.objects.filter(special_day_id=christmas.id).exists()
    )


def test_one_special_day_per_date_said_under_the_date():
    make_special_day("2026-12-25", "Christmas")
    with pytest.raises(Conflict) as refused:
        run(
            "schedule.special_day.create", SpecialDayIn(date="2026-12-25", name="Again")
        )
    assert refused.value.code == "schedule.special_day_exists"
    assert refused.value.fields == {
        "date": "There is already a special day on that date."
    }
    assert SpecialDay.objects.count() == 1 and outbox() == []


def test_a_deleted_special_day_frees_its_date():
    christmas = make_special_day("2026-12-25", "Christmas")
    deleted = run(
        "schedule.special_day.delete", SpecialDayRefIn(special_day="Christmas")
    )
    assert deleted.id == christmas.id
    assert outbox() == [
        ("schedule.special_day.deleted", A.key, {"id": str(christmas.id)})
    ]
    again = run(
        "schedule.special_day.create", SpecialDayIn(date="2026-12-25", name="Christmas")
    )
    assert SpecialDay.objects.get().id == again.id


def test_deleting_takes_the_intervals_and_a_missing_day_says_so():
    eve = make_special_day("2026-12-24", "Eve", ("10:00", "13:00"))
    run("schedule.special_day.delete", SpecialDayRefIn(id=eve.id))
    assert not SpecialDayInterval.objects.exists()
    with pytest.raises(NotFound) as refused:
        run("schedule.special_day.delete", SpecialDayRefIn(id=eve.id))
    assert refused.value.message == "That special day does not exist in this business."
    assert names() == ["schedule.special_day.deleted"]


def test_correcting_a_special_day_changes_only_what_is_sent():
    christmas = make_special_day("2026-12-25", "Christmas", notes="Family")
    fixed = run(
        "schedule.special_day.update",
        SpecialDayPatchIn(
            special_day="2026-12-25",
            is_closed=False,
            intervals=hours(("10:00", "14:00")),
        ),
    )
    assert (fixed.name, fixed.notes, fixed.is_closed) == ("Christmas", "Family", False)
    assert [(i.open_time, i.close_time) for i in fixed.intervals] == [
        (t("10:00"), t("14:00"))
    ]
    assert outbox() == [
        (
            "schedule.special_day.updated",
            A.key,
            {"id": str(christmas.id), "date": "2026-12-25"},
        )
    ]
    # Moving it to another date, and closing it again: its intervals go.
    run(
        "schedule.special_day.update",
        SpecialDayPatchIn(id=christmas.id, date="2026-12-26", is_closed=True),
    )
    row = SpecialDay.objects.get(pk=christmas.id)
    assert (row.date, row.is_closed, row.intervals.count()) == (
        dt.date(2026, 12, 26),
        True,
        0,
    )


def test_saving_a_special_day_unchanged_says_nothing():
    christmas = make_special_day("2026-12-25", "Christmas")
    run(
        "schedule.special_day.update",
        SpecialDayPatchIn(id=christmas.id, name="Christmas", is_closed=True),
    )
    assert outbox() == []


def test_a_correction_follows_the_same_rules():
    make_special_day("2026-12-25", "Christmas")
    eve = make_special_day("2026-12-24", "Eve")
    with pytest.raises(Conflict) as refused:
        run(
            "schedule.special_day.update",
            SpecialDayPatchIn(id=eve.id, date="2026-12-25"),
        )
    assert refused.value.fields == {
        "date": "There is already a special day on that date."
    }
    with pytest.raises(InvalidPayload) as refused:
        run(
            "schedule.special_day.update", SpecialDayPatchIn(id=eve.id, is_closed=False)
        )
    assert refused.value.fields == {
        "intervals": "An open day needs at least one opening interval."
    }
    with pytest.raises(InvalidPayload) as refused:
        run(
            "schedule.special_day.update",
            SpecialDayPatchIn(
                id=eve.id,
                is_closed=False,
                intervals=hours(("09:00", "14:00"), ("13:00", "18:00")),
            ),
        )
    assert "intervals" in refused.value.fields
    assert outbox() == []


def test_new_intervals_of_an_open_special_day_replace_the_old_ones():
    eve = make_special_day("2026-12-24", "Eve", ("10:00", "13:00"), ("17:00", "19:00"))
    run(
        "schedule.special_day.update",
        SpecialDayPatchIn(id=eve.id, intervals=hours(("09:00", "12:00"))),
    )
    assert [(i.open_time, i.close_time) for i in eve.intervals.all()] == [
        (t("09:00"), t("12:00"))
    ]


def test_the_bulk_creates_the_valid_days_and_skips_the_rest_with_their_reason():
    make_special_day("2026-12-25", "Christmas")
    result = run(
        "schedule.special_day.bulk_create",
        BulkSpecialDayIn(
            special_days=[
                {"date": "2026-12-25", "name": "Christmas again"},
                {"date": "2026-12-26", "name": "Boxing day"},
                {"date": "2026-12-26", "name": "Duplicate in the list"},
                {
                    "date": "2026-12-24",
                    "name": "Eve",
                    "is_closed": False,
                    "intervals": [],
                },
                {
                    "date": "2026-12-31",
                    "name": "New Year's Eve",
                    "is_closed": False,
                    "intervals": hours(("10:00", "14:00")),
                },
            ]
        ),
    )
    assert [(s.index, s.date, s.code) for s in result.skipped] == [
        (0, dt.date(2026, 12, 25), "already_exists"),
        (2, dt.date(2026, 12, 26), "already_exists"),
        (3, dt.date(2026, 12, 24), "invalid_hours"),
    ]
    assert (
        result.skipped[2].message == "An open day needs at least one opening interval."
    )
    assert len(result.created) == 2
    assert sorted(SpecialDay.objects.values_list("name", flat=True)) == [
        "Boxing day",
        "Christmas",
        "New Year's Eve",
    ]
    assert names() == ["schedule.special_day.created", "schedule.special_day.created"]


def test_a_bulk_that_creates_nothing_says_nothing():
    make_special_day("2026-12-25", "Christmas")
    result = run(
        "schedule.special_day.bulk_create",
        BulkSpecialDayIn(special_days=[{"date": "2026-12-25", "name": "X"}]),
    )
    assert result.created == [] and outbox() == []


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_special_days_on_the_same_date_at_once_keep_one():
    # No lock of the settings: the second waits at its insert of the same date until the first commits, same 409.
    def create(name):
        return lambda: run(
            "schedule.special_day.create", SpecialDayIn(date="2026-12-25", name=name)
        )

    outcome = _race(create("First"), create("Second"))
    assert (
        isinstance(outcome.get("error"), Conflict)
        and outcome["error"].code == "schedule.special_day_exists"
    )
    assert list(SpecialDay.objects.values_list("name", flat=True)) == ["First"]


def test_a_day_of_the_bulk_with_thirteen_intervals_is_skipped_and_the_rest_go_in():
    # SCHEDULE-F07: a day whose hours are not valid is skipped with its reason, never the whole list.
    thirteen = hours(*[(f"{hour:02d}:00", f"{hour:02d}:30") for hour in range(13)])
    result = run(
        "schedule.special_day.bulk_create",
        BulkSpecialDayIn(
            special_days=[
                {"date": "2026-12-24", "name": "Eve", "is_closed": False, "intervals": thirteen},
                {"date": "2026-12-25", "name": "Christmas"},
            ]
        ),
    )
    assert [(s.index, s.code, s.message) for s in result.skipped] == [(0, "invalid_hours", "At most 12 intervals a day.")]
    assert list(SpecialDay.objects.values_list("name", flat=True)) == ["Christmas"]


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_a_day_of_the_bulk_taken_at_the_same_time_is_skipped_not_the_whole_list():
    def first():
        return run("schedule.special_day.create", SpecialDayIn(date="2026-12-25", name="First"))

    def bulk():
        return run(
            "schedule.special_day.bulk_create",
            BulkSpecialDayIn(special_days=[{"date": "2026-12-25", "name": "Christmas"}, {"date": "2026-12-26", "name": "Boxing day"}]),
        )

    outcome = _race(first, bulk)
    assert "result" in outcome, outcome
    assert [(s.index, s.code) for s in outcome["result"].skipped] == [(0, "already_exists")]
    assert sorted(SpecialDay.objects.values_list("name", flat=True)) == ["Boxing day", "First"]


def test_correcting_a_special_day_with_a_split_shift_keeps_every_interval_sent():
    # SCHEDULE-F13: the intervals sent replace them all, every one of them, sorted.
    eve = make_special_day("2026-12-24", "Christmas Eve", ("10:00", "13:00"))
    fixed = run(
        "schedule.special_day.update",
        SpecialDayPatchIn(id=eve.id, intervals=hours(("17:00", "20:00"), ("09:00", "14:00"))),
    )
    assert [(i.open_time, i.close_time) for i in fixed.intervals] == [
        (t("09:00"), t("14:00")),
        (t("17:00"), t("20:00")),
    ]
    assert SpecialDay.objects.get(pk=eve.id).intervals.count() == 2
