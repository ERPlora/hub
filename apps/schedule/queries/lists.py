"""The lists of the special days and of the temporary changes: search, filters, a stable sort and pages."""

from typing import Any

from django.db.models import QuerySet
from live.context import OperationContext
from live.operations import operation

from apps.schedule.schemas.fields import PageIn
from apps.schedule.schemas.overrides import OverrideListIn, OverridePage
from apps.schedule.schemas.special_days import SpecialDayListIn, SpecialDayPage
from base.ordering import list_order
from base.text_search import contains_text

from .outputs import override_out, special_day_out
from .rows import overrides, special_days

SPECIAL_DAY_SORTS = {
    "date": ("date",),
    "name": ("name",),
    "is_closed": ("is_closed", "date"),
    "recurring_yearly": ("recurring_yearly", "date"),
    "id": (),
}
OVERRIDE_SORTS = {
    "start_date": ("start_date",),
    "end_date": ("end_date",),
    "reason": ("reason",),
    "is_closed": ("is_closed", "start_date"),
    "id": (),
}


def _page(rows: QuerySet[Any], params: PageIn, out: Any) -> dict:
    return {
        "rows": [
            out(row) for row in rows[params.offset : params.offset + params.limit]
        ],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "schedule.special_day.list",
    kind="query",
    permission="schedule.view",
    input=SpecialDayListIn,
    output=SpecialDayPage,
    expose_api=True,
    ai={
        "description": "Lists the special days (holidays, closures, days with other hours) with their intervals.",
        "asks": {
            "en": (
                "which holidays have we got on the calendar?",
                "list the special days of this year",
            ),
            "es": (
                "¿qué festivos tenemos apuntados este año?",
                "dime las fiestas y las fechas especiales del calendario",
            ),
        },
    },
)
def list_special_days(ctx: OperationContext, params: SpecialDayListIn) -> dict:
    rows = special_days()
    if params.search:
        rows = rows.filter(contains_text(params.search, "name", "notes"))
    if params.name:
        rows = rows.filter(contains_text(params.name, "name"))
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_closed is not None:
        rows = rows.filter(is_closed=params.is_closed)
    if params.recurring_yearly is not None:
        rows = rows.filter(recurring_yearly=params.recurring_yearly)
    return _page(
        rows.order_by(*list_order(*SPECIAL_DAY_SORTS[params.sort], descending=params.dir == "desc")),
        params,
        special_day_out,
    )


@operation(
    "schedule.override.list",
    kind="query",
    permission="schedule.view",
    input=OverrideListIn,
    output=OverridePage,
    expose_api=True,
    ai={
        "description": "Lists the temporary changes of the opening hours (a range of dates closed or with other "
        "hours).",
        "asks": {
            "en": (
                "which temporary changes of the opening are planned?",
                "is there a summer closure planned?",
            ),
            "es": (
                "¿qué cambios temporales de apertura hay programados?",
                "¿cuándo cerramos por vacaciones o hacemos horario de verano?",
                "¿hay alguna temporada de reformas con otra apertura?",
            ),
        },
    },
)
def list_overrides(ctx: OperationContext, params: OverrideListIn) -> dict:
    rows = overrides()
    if params.search:
        rows = rows.filter(contains_text(params.search, "reason"))
    if params.reason:
        rows = rows.filter(contains_text(params.reason, "reason"))
    for field, lookup in (
        ("start_from", "start_date__gte"),
        ("start_to", "start_date__lte"),
        ("end_from", "end_date__gte"),
        ("end_to", "end_date__lte"),
    ):
        if getattr(params, field):
            rows = rows.filter(**{lookup: getattr(params, field)})
    if params.is_closed is not None:
        rows = rows.filter(is_closed=params.is_closed)
    return _page(
        rows.order_by(*list_order(*OVERRIDE_SORTS[params.sort], descending=params.dir == "desc")), params, override_out
    )
