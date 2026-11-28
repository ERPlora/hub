"""What of Schedules travels in an export of the business (BASE-F35): the usual week, the special days and the
temporary changes, each with its opening hours, read with Schedules' own reads and written with its own writes. A day of
the week is named by its number, a special day by its date and a temporary change by its first day.

The week a business is born with is the default one nobody confirmed: it is not the business's, so it neither travels
nor counts, and a file's week takes its place. A week the business confirmed is its own and a file never overwrites it.
The week stays when a load is undone or the app is reset, like the rest of the business's settings."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from pydantic import ValidationError

from base.blueprint.calls import Dataset, Loaded, as_text, by_name, call, count_of, given, ids_of, reason, remover
from base.blueprint.calls import rows_of, text_of
from base.weekdays import weekday_name

DAY_FIELDS = ("weekday", "is_closed", "intervals")
SPECIAL_DAY_FIELDS = ("date", "name", "is_closed", "recurring_yearly", "notes", "intervals")
CHANGE_FIELDS = ("start_date", "end_date", "reason", "is_closed", "intervals")


def _week_rows(ctx: OperationContext) -> list[dict]:
    week = call(ctx, "schedule.week.get")
    if not week.confirmed:
        return []
    return [{field: as_text(getattr(day, field)) for field in DAY_FIELDS} for day in week.days if day.is_set]


def _day_label(row: dict) -> str:
    day = row.get("weekday")
    return weekday_name(day) if day in range(7) else text_of(row, "weekday")


def _week_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    if call(ctx, "schedule.week.get").confirmed:
        loaded.already += len(rows)
        return
    for row in rows:
        try:
            week = call(ctx, "schedule.week.set_day", **given(row, DAY_FIELDS))
        except (OperationError, ValidationError) as exc:
            loaded.refuse(_day_label(row), reason(exc))
            continue
        loaded.created += [str(day.id) for day in week.days if day.weekday == row["weekday"]]


DATASETS = [
    Dataset(
        key="schedule.week",
        label=_("Usual week"),
        rows=_week_rows,
        count=lambda ctx: len(_week_rows(ctx)),
        load=_week_load,
        models=("WeekDay", "WeekDayInterval"),
    ),
    Dataset(
        key="schedule.special_day",
        label=_("Special days"),
        rows=rows_of("schedule.special_day.list", SPECIAL_DAY_FIELDS),
        ids=ids_of("schedule.special_day.list"),
        count=count_of("schedule.special_day.list"),
        load=by_name("schedule.special_day.list", "schedule.special_day.create", SPECIAL_DAY_FIELDS, named="date"),
        remove=remover("schedule.special_day.delete"),
        models=("SpecialDay", "SpecialDayInterval"),
    ),
    Dataset(
        key="schedule.override",
        label=_("Temporary changes"),
        rows=rows_of("schedule.override.list", CHANGE_FIELDS),
        ids=ids_of("schedule.override.list"),
        count=count_of("schedule.override.list"),
        load=by_name("schedule.override.list", "schedule.override.create", CHANGE_FIELDS, named="start_date"),
        remove=remover("schedule.override.delete"),
        models=("Override", "OverrideInterval"),
    ),
]
