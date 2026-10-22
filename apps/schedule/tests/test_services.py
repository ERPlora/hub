"""Write operations of the schedule app: one operation = one transaction with its events in the outbox.

A refused command leaves no trace (no row, no event). Cases from the old module's WORKFLOW
(SCHEDULES-F02 … F08) and its handler and engine tests (schedules#2, #7, #8, #23, #43), plus the
corrections of the port (SCHEDULE-F13, freed dates).
"""

import datetime as dt
import threading

import pytest
from django.db import connection, transaction
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.schedule.models import (
    Override,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
)
from apps.schedule.schemas import (
    BulkSpecialDayIn,
    NoParamsIn,
    OverrideIn,
    OverridePatchIn,
    OverrideRefIn,
    SetDayIn,
    SettingsIn,
    SpecialDayIn,
    SpecialDayPatchIn,
    SpecialDayRefIn,
)

from .conftest import B, ctx_for, make_day, make_override, make_special_day

pytestmark = pytest.mark.django_db

QUIET = 0.3


def run(name, data, role="hub_admin", **ctx):
    return get(name)(ctx_for(role, **ctx), data)


def outbox():
    return list(
        OutboxEvent.objects.order_by("id").values_list("name", "scope_key", "payload")
    )


def names():
    return [name for name, _, _ in outbox()]


def t(value):
    return dt.time.fromisoformat(value)


def hours(*pairs):
    return [{"open_time": start, "close_time": end} for start, end in pairs]


def stored(day: int):
    row = WeekDay.objects.get(weekday=day)
    return row.is_closed, [
        (i.position, i.open_time, i.close_time)
        for i in row.intervals.order_by("position")
    ]


def confirmed() -> bool:
    return ScheduleSettings.objects.filter(hours_confirmed=True).exists()


# ── Permissions ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "data", "permission"),
    [
        (
            "schedule.week.set_day",
            lambda: SetDayIn(weekday=0, is_closed=True),
            "schedule.change",
        ),
        ("schedule.week.confirm", lambda: NoParamsIn(), "schedule.change"),
        (
            "schedule.special_day.create",
            lambda: SpecialDayIn(date="2026-12-25", name="Christmas"),
            "schedule.add",
        ),
        (
            "schedule.special_day.bulk_create",
            lambda: BulkSpecialDayIn(
                special_days=[{"date": "2026-12-25", "name": "Christmas"}]
            ),
            "schedule.add",
        ),
        (
            "schedule.special_day.update",
            lambda: SpecialDayPatchIn(special_day="Christmas", notes="x"),
            "schedule.change",
        ),
        (
            "schedule.special_day.delete",
            lambda: SpecialDayRefIn(special_day="Christmas"),
            "schedule.delete",
        ),
        (
            "schedule.override.create",
            lambda: OverrideIn(
                start_date="2026-08-01", end_date="2026-08-02", reason="x"
            ),
            "schedule.add",
        ),
        (
            "schedule.override.update",
            lambda: OverridePatchIn(override="Holidays", reason="y"),
            "schedule.change",
        ),
        (
            "schedule.override.delete",
            lambda: OverrideRefIn(override="Holidays"),
            "schedule.delete",
        ),
        (
            "schedule.settings.update",
            lambda: SettingsIn(week_starts_on=7),
            "schedule.manage_settings",
        ),
    ],
)
def test_an_employee_only_looks_and_each_action_needs_its_permission(
    name, data, permission
):
    make_special_day("2026-12-24", "Christmas")
    make_override("2026-03-01", "2026-03-02", "Holidays")
    with pytest.raises(PermissionDenied):
        run(name, data(), "hub_employee")
    with pytest.raises(PermissionDenied):
        run(name, data(), permissions={"schedule.view"})
    assert outbox() == []
    run(name, data(), permissions={"schedule.view", permission})


# ── The week (SCHEDULE-F02, F03) ───────────────────────────────────────────────────────────────


def test_saving_a_day_replaces_its_intervals_sorted_and_confirms_the_week():
    week = run(
        "schedule.week.set_day",
        SetDayIn(weekday=0, intervals=hours(("17:00", "20:00"), ("10:00", "14:00"))),
    )
    assert stored(0) == (
        False,
        [(0, t("10:00"), t("14:00")), (1, t("17:00"), t("20:00"))],
    )
    assert confirmed()
    assert [i.open_time for i in week.days[0].intervals] == [t("10:00"), t("17:00")]
    assert outbox() == [("schedule.week.updated", "a", {"weekday": 0})]
    # Saving again replaces, never adds.
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=0, intervals=hours(("09:00", "13:00"))),
    )
    assert stored(0) == (False, [(0, t("09:00"), t("13:00"))])


def test_a_closed_day_keeps_no_interval_and_an_unset_day_is_created():
    WeekDay.objects.filter(weekday=6).delete()
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=6, is_closed=True, intervals=hours(("10:00", "14:00"))),
    )
    assert stored(6) == (True, [])
    run(
        "schedule.week.set_day",
        SetDayIn(weekday="sábado", intervals=hours(("00:00", "00:00"))),
    )
    assert stored(5) == (False, [(0, t("00:00"), t("00:00"))])
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=4, intervals=hours(("22:00", "02:00"))),
    )
    assert stored(4) == (False, [(0, t("22:00"), t("02:00"))])


def test_the_live_notice_goes_to_the_callers_scope_only():
    run("schedule.week.set_day", SetDayIn(weekday=1, is_closed=True), scope=B)
    assert outbox() == [("schedule.week.updated", "b", {"weekday": 1})]


def test_confirming_the_default_week_changes_no_hour():
    before = [stored(day) for day in range(7)]
    week = run("schedule.week.confirm", NoParamsIn())
    assert week.confirmed and confirmed()
    assert [stored(day) for day in range(7)] == before
    assert names() == ["schedule.week.updated"]
    # Confirming twice changes nothing and says nothing.
    run("schedule.week.confirm", NoParamsIn())
    assert names() == ["schedule.week.updated"]


def test_a_week_that_is_not_there_cannot_be_confirmed():
    WeekDay.objects.all().delete()
    with pytest.raises(Conflict) as refused:
        run("schedule.week.confirm", NoParamsIn())
    assert refused.value.code == "schedule.no_week"
    assert refused.value.message == "There are no weekly opening hours to confirm."
    assert not confirmed() and outbox() == []


# ── Special days (SCHEDULE-F04, F06, F07, F13) ─────────────────────────────────────────────────


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
        ("schedule.special_day.created", "a", {"id": str(eve.id), "date": "2026-12-24"})
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
        ("schedule.special_day.deleted", "a", {"id": str(christmas.id)})
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
            "a",
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


# ── Temporary changes (SCHEDULE-F05, F06, F13) ─────────────────────────────────────────────────


def test_a_temporary_change_with_its_intervals():
    summer = run(
        "schedule.override.create",
        OverrideIn(
            start_date="2026-08-01",
            end_date="2026-08-31",
            reason="Summer",
            is_closed=False,
            intervals=hours(("18:00", "21:00"), ("10:00", "13:30")),
        ),
    )
    row = Override.objects.get(pk=summer.id)
    assert (row.reason, row.is_closed) == ("Summer", False)
    assert [(i.position, i.open_time) for i in row.intervals.order_by("position")] == [
        (0, t("10:00")),
        (1, t("18:00")),
    ]
    assert outbox() == [
        (
            "schedule.override.created",
            "a",
            {
                "id": str(summer.id),
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
            },
        )
    ]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-08-28", "2026-08-30"),
        ("2026-07-01", "2026-08-01"),
        ("2026-08-31", "2026-09-05"),
    ],
)
def test_two_temporary_changes_never_cover_the_same_day(start, end):
    make_override("2026-08-01", "2026-08-31", "Vacaciones")
    with pytest.raises(Conflict) as refused:
        run(
            "schedule.override.create",
            OverrideIn(start_date=start, end_date=end, reason="More holidays"),
        )
    assert refused.value.code == "schedule.override_overlaps"
    assert refused.value.fields == {
        "start_date": "Those dates overlap the temporary change “Vacaciones” (08/01/2026 – 08/31/2026)."
    }
    assert Override.objects.count() == 1 and outbox() == []


def test_touching_temporary_changes_are_fine():
    make_override("2026-08-01", "2026-08-15", "First half")
    run(
        "schedule.override.create",
        OverrideIn(
            start_date="2026-08-16", end_date="2026-08-31", reason="Second half"
        ),
    )
    assert Override.objects.count() == 2


def test_correcting_a_temporary_change():
    summer = make_override("2026-07-01", "2026-08-31", "Summer", ("10:00", "14:00"))
    make_override("2026-09-10", "2026-09-12", "Works")
    fixed = run(
        "schedule.override.update",
        OverridePatchIn(override="summer", end_date="2026-09-05"),
    )
    assert (fixed.start_date, fixed.end_date, fixed.reason, fixed.is_closed) == (
        dt.date(2026, 7, 1),
        dt.date(2026, 9, 5),
        "Summer",
        False,
    )
    assert outbox() == [
        (
            "schedule.override.updated",
            "a",
            {
                "id": str(summer.id),
                "start_date": "2026-07-01",
                "end_date": "2026-09-05",
            },
        )
    ]
    # Over the next change: refused; its own range never clashes with itself.
    with pytest.raises(Conflict):
        run(
            "schedule.override.update",
            OverridePatchIn(id=summer.id, end_date="2026-09-10"),
        )
    with pytest.raises(InvalidPayload) as refused:
        run(
            "schedule.override.update",
            OverridePatchIn(id=summer.id, start_date="2026-09-06"),
        )
    assert refused.value.fields == {
        "end_date": "The end date cannot be before the start date."
    }
    run("schedule.override.update", OverridePatchIn(id=summer.id, is_closed=True))
    assert Override.objects.get(pk=summer.id).intervals.count() == 0


def test_deleting_a_temporary_change_by_a_date_it_covers():
    summer = make_override("2026-07-01", "2026-08-31", "Summer", ("10:00", "14:00"))
    run("schedule.override.delete", OverrideRefIn(override="2026-08-15"))
    assert not Override.objects.exists()
    assert outbox() == [("schedule.override.deleted", "a", {"id": str(summer.id)})]
    with pytest.raises(NotFound):
        run("schedule.override.delete", OverrideRefIn(override="Summer"))


# ── Settings (SCHEDULE-F08) ────────────────────────────────────────────────────────────────────


def test_the_first_save_of_the_settings_creates_them_and_a_change_says_so():
    ScheduleSettings.objects.all().delete()
    saved = run("schedule.settings.update", SettingsIn(week_starts_on=7))
    assert (saved.week_starts_on, saved.timezone) == (7, "Europe/Madrid")
    assert ScheduleSettings.objects.get().week_starts_on == 7
    assert names() == ["schedule.settings.updated"]
    run("schedule.settings.update", SettingsIn(week_starts_on=7))
    run("schedule.settings.update", SettingsIn())
    assert names() == ["schedule.settings.updated"]


def test_saving_the_settings_never_touches_the_confirmation():
    ScheduleSettings.objects.create(hours_confirmed=True)
    run("schedule.settings.update", SettingsIn(week_starts_on=1))
    assert confirmed()


# ── Two people at the same instant ─────────────────────────────────────────────────────────────


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


def _race(first, second):
    """Run ``first`` in a transaction kept open until ``second`` (another thread) is blocked on it."""
    done, release = threading.Event(), threading.Event()

    def held():
        with transaction.atomic():
            result = first()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(second)
    waiter.join(QUIET)
    waited = waiter.is_alive()
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
    assert waited, "the second call did not wait for the first one's lock"
    return outcome


@pytest.mark.django_db(transaction=True)
def test_two_overlapping_temporary_changes_at_once_keep_one():
    def create(start, end, reason):
        return lambda: run(
            "schedule.override.create",
            OverrideIn(start_date=start, end_date=end, reason=reason),
        )

    outcome = _race(
        create("2026-08-01", "2026-08-15", "First"),
        create("2026-08-10", "2026-08-20", "Second"),
    )
    assert (
        isinstance(outcome.get("error"), Conflict)
        and outcome["error"].code == "schedule.override_overlaps"
    )
    assert list(Override.objects.values_list("reason", flat=True)) == ["First"]


@pytest.mark.django_db(transaction=True)
def test_two_special_days_on_the_same_date_at_once_keep_one():
    # No lock to wait for: the unique date stops the second at its COMMIT-time insert, same 409.
    def create(name):
        return lambda: run(
            "schedule.special_day.create", SpecialDayIn(date="2026-12-25", name=name)
        )

    done, release = threading.Event(), threading.Event()

    def held():
        with transaction.atomic():
            result = create("First")()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(create("Second"))
    waiter.join(QUIET)
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
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


@pytest.mark.django_db(transaction=True)
def test_a_day_of_the_bulk_taken_at_the_same_time_is_skipped_not_the_whole_list():
    def first():
        return run("schedule.special_day.create", SpecialDayIn(date="2026-12-25", name="First"))

    def bulk():
        return run(
            "schedule.special_day.bulk_create",
            BulkSpecialDayIn(special_days=[{"date": "2026-12-25", "name": "Christmas"}, {"date": "2026-12-26", "name": "Boxing day"}]),
        )

    done, release = threading.Event(), threading.Event()

    def held():
        with transaction.atomic():
            result = first()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(bulk)
    waiter.join(QUIET)
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
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
