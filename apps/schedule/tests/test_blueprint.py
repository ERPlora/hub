"""What of Schedules travels in an export of the business (BASE-F35): the usual week, the special days and the
temporary changes, read with Schedules' own reads and written with its own writes, so that loading the file in a new
business brings its opening hours back as they were.

The week every business is born with (Monday to Friday 09:00–18:00, the weekend closed, that nobody confirmed) is not the
business's own: it does not travel, it does not count as something the business already has, and it is what the week of
a file replaces. A week the business confirmed is its own: a file never overwrites it.

Every test runs against the real apps, in business A's own database, as production does.
"""

from apps.schedule.models import ScheduleSettings
from apps.schedule.tests.conftest import HUB_DB, in_business_a, make_day
from base.blueprint.export import counts
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

SPLIT = [{"open_time": "09:00", "close_time": "13:00"}, {"open_time": "16:00", "close_time": "20:00"}]
CHRISTMAS = {"date": "2026-12-25", "name": "Christmas", "is_closed": True, "recurring_yearly": True, "intervals": []}
NEW_YEARS_EVE = {"date": "2026-12-31", "name": "New Year's Eve", "is_closed": False, "notes": "Short day",
                 "intervals": [{"open_time": "10:00", "close_time": "14:00"}]}  # fmt: skip
SUMMER = {"start_date": "2026-08-01", "end_date": "2026-08-31", "reason": "Summer hours", "is_closed": False,
          "intervals": [{"open_time": "08:00", "close_time": "15:00"}]}  # fmt: skip


def our_hours(ctx):
    call(ctx, "schedule.week.set_day", weekday=0, is_closed=False, intervals=SPLIT)
    call(ctx, "schedule.week.set_day", weekday=6, is_closed=True, intervals=[])
    for special in (CHRISTMAS, NEW_YEARS_EVE):
        call(ctx, "schedule.special_day.create", **special)
    call(ctx, "schedule.override.create", **SUMMER)


def hours(intervals) -> list[tuple[str, str]]:
    return [(f"{i.open_time:%H:%M}", f"{i.close_time:%H:%M}") for i in intervals]


def the_hours(ctx) -> dict:
    """The week, the special days and the temporary changes as the business reads them, without ids."""
    week = call(ctx, "schedule.week.get")
    specials = call(ctx, "schedule.special_day.list", limit=100).rows
    changes = call(ctx, "schedule.override.list", limit=100).rows
    return {
        "confirmed": week.confirmed,
        "week": [(day.weekday, day.is_set, day.is_closed, hours(day.intervals)) for day in week.days],
        "special_days": [(row.date, row.name, row.is_closed, row.recurring_yearly, row.notes, hours(row.intervals))
                         for row in specials],  # fmt: skip
        "changes": [(row.start_date, row.end_date, row.reason, row.is_closed, hours(row.intervals)) for row in changes],
    }


def born_again(ctx) -> None:
    """The business as a new one is born: the default week, unconfirmed, and no special day or temporary change."""
    for weekday in range(5):
        make_day(weekday, ("09:00", "18:00"))
    for weekday in (5, 6):
        make_day(weekday, closed=True)
    ScheduleSettings.objects.update(hours_confirmed=False)
    for row in call(ctx, "schedule.special_day.list", limit=100).rows:
        call(ctx, "schedule.special_day.delete", id=row.id)
    for row in call(ctx, "schedule.override.list", limit=100).rows:
        call(ctx, "schedule.override.delete", id=row.id)


def created_and_already(report: dict) -> dict:
    return {part["key"]: (part["created"], part["already"]) for part in app_report(report, "schedule")["datasets"]}


def test_a_backup_brings_the_week_the_special_days_and_the_temporary_changes_back_to_a_new_business(ctx):
    our_hours(ctx)
    before = the_hours(ctx)
    file = exported(ctx, ["schedule"])
    born_again(ctx)

    report = loaded_back(ctx, file)

    assert the_hours(ctx) == before
    assert created_and_already(report) == {
        "schedule.week": (7, 0),
        "schedule.special_day": (2, 0),
        "schedule.override": (1, 0),
    }


def test_loading_the_file_again_duplicates_nothing_and_keeps_the_week_the_business_confirmed(ctx):
    our_hours(ctx)
    file = exported(ctx, ["schedule"])
    call(ctx, "schedule.week.set_day", weekday=0, is_closed=True, intervals=[])
    before = the_hours(ctx)

    report = loaded_back(ctx, file)

    assert the_hours(ctx) == before
    assert created_and_already(report) == {
        "schedule.week": (0, 7),
        "schedule.special_day": (0, 2),
        "schedule.override": (0, 1),
    }


def test_the_default_week_nobody_confirmed_neither_travels_nor_counts_as_the_business_s_own(ctx):
    born_again(ctx)

    assert counts(ctx)["schedule.week"] == 0
    assert "schedule.week" not in data_of(ctx, ["schedule"])


def test_a_confirmed_week_travels_day_by_day_with_its_hours(ctx):
    our_hours(ctx)

    week = data_of(ctx, ["schedule"])["schedule.week"]

    assert counts(ctx)["schedule.week"] == 7
    assert week[0] == {"weekday": 0, "is_closed": False, "intervals": SPLIT}
    assert week[6] == {"weekday": 6, "is_closed": True, "intervals": []}
