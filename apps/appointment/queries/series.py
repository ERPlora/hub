"""The repeating appointments (series): their list, one with its next date, and how one is named."""

import datetime as dt
from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.appointment import engine
from apps.appointment.models import Appointment, Recurring
from apps.appointment.schemas.series import RecurringDetailOut, RecurringGetIn, RecurringListIn, RecurringPage
from base.ordering import list_order_for
from base.text_search import contains_text
from base.weekdays import weekday_name

from .access import VIEW_OWN
from .business import day_bounds, now, today
from .ownership import SERIES
from .reads import MOVABLE, _page

#: The window a series books when the maximum advance is 0 (no limit).
SERIES_DEFAULT_WINDOW = 90

RECURRING_NOT_FOUND = _("That repeating appointment does not exist in this business.")


def series_with_lines() -> QuerySet[Recurring]:
    """The series with the services they book (what ``series_out`` shows)."""
    return Recurring.objects.prefetch_related("lines__service")


def series_rows(ctx: OperationContext) -> QuerySet[Recurring]:
    """The live series the caller may see (``SERIES``), with the services they book."""
    return SERIES.visible(ctx).filter(deleted_at__isnull=True).prefetch_related("lines__service")


def find_series(
    ctx: OperationContext, series_id: UUID, *, lock: bool = False, lines: bool = False
) -> Recurring:
    """The live series the caller may see (``NotFound`` otherwise), with its services when ``lines`` (what its detail
    shows): one read, so a deletion committed meanwhile is either not seen yet or not found, never a series that
    vanished or changed between two reads."""
    rows = (series_rows(ctx) if lines else SERIES.visible(ctx).filter(deleted_at__isnull=True)).filter(pk=series_id)
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = rows.first()
    if found is None:
        raise NotFound(str(RECURRING_NOT_FOUND), code="appointment.recurring_not_found")
    return found


def pattern_of(series: Recurring) -> engine.Pattern:
    return engine.Pattern(
        series.frequency,
        series.day_of_week,
        series.start_date,
        series.end_date,
        series.max_occurrences,
    )


def series_out(series: Recurring) -> dict:
    lines = [
        {"service_id": line.service_id, "name": line.service.name}
        for line in series.lines.all()
    ]
    return {
        "id": series.id,
        "customer_id": series.customer_id,
        "customer_name": series.customer_name,
        "staff_id": series.staff_id,
        "staff_name": series.staff_name,
        "services": lines,
        "service_names": ", ".join(line["name"] for line in lines),
        "frequency": series.frequency,
        "day_of_week": series.day_of_week,
        "time": series.time,
        "duration_minutes": series.duration_minutes,
        "start_date": series.start_date,
        "end_date": series.end_date,
        "max_occurrences": series.max_occurrences,
        "is_active": series.is_active,
        "split_from_id": series.split_from_id,
        "created_at": series.created_at,
    }


def load_series(series_id: UUID) -> dict:
    return series_out(series_with_lines().get(pk=series_id))


RECURRING_ORDER = {
    "customer_name": ("customer_name",),
    "staff_name": ("staff_name",),
    "start_date": ("start_date",),
    "time": ("time",),
}


@operation(
    "appointment.recurring.list",
    kind="query",
    permission=VIEW_OWN,
    input=RecurringListIn,
    output=RecurringPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which repeating appointments do we have?",
                "list the recurring appointments that are still running",
            ),
            "es": (
                "¿qué citas fijas que se repiten tenemos?",
                "las citas recurrentes que siguen en marcha",
            ),
        },
        "description": "List the repeating appointments (series) with customer, services, professional, rule and "
        "whether they are active; search by a name, filter by active, repetition or professional."
    },
)
def list_series(ctx: OperationContext, params: RecurringListIn) -> dict:
    rows = series_rows(ctx)
    if params.search:
        text = params.search
        rows = rows.filter(contains_text(text, "customer_name", "staff_name", "lines__service__name")).distinct()
    if params.is_active is not None:
        rows = rows.filter(is_active=params.is_active)
    if params.frequency:
        rows = rows.filter(frequency=params.frequency)
    if params.staff_id:
        rows = rows.filter(staff_id=params.staff_id)
    return _page(
        rows.order_by(*list_order_for(params.sort, columns=RECURRING_ORDER)),
        params.limit,
        params.offset,
        series_out,
    )


def series_label(series: Recurring) -> str:
    """How a person names ``series`` in the active language, as each card of the series list is titled: its customer
    (nothing once her data were erased), its repetition, its weekday (only a weekly or biweekly one keeps one) and its
    hour."""
    weekday = "" if series.day_of_week is None else weekday_name(series.day_of_week)
    parts = (series.customer_name, series.get_frequency_display(), weekday, f"{series.time:%H:%M}")
    return " · ".join(str(part) for part in parts if part)


def series_reach(series: Recurring, from_date: dt.date) -> tuple[int, int]:
    """``(upcoming, charged)``: the live appointments of the series from ``from_date`` on, and how many are charged."""
    start, _ = day_bounds(from_date, from_date)
    rows = Appointment.objects.filter(
        deleted_at__isnull=True, recurring=series, status__in=MOVABLE, start__gte=max(start, now())
    )
    counts = rows.aggregate(
        upcoming=Count("id"), charged=Count("id", filter=Q(sale_id__isnull=False))
    )
    return counts["upcoming"], counts["charged"]


@operation(
    "appointment.recurring.get",
    kind="query",
    permission=VIEW_OWN,
    input=RecurringGetIn,
    output=RecurringDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "when is the next date of Paula's weekly appointment?",
                "show me Paula's repeating appointment in detail",
            ),
            "es": (
                "¿cuándo toca la próxima cita fija de Paula?",
                "dame el detalle de la cita fija de Paula",
            ),
        },
        "description": "One repeating appointment with its next date and how many booked appointments an edit from a "
        "date would reach (and how many of those are charged, which an edit never touches)."
    },
)
def get_series(ctx: OperationContext, data: RecurringGetIn) -> dict:
    series = find_series(ctx, data.id, lines=True)
    dates, upcoming_date = engine.dates(pattern_of(series), until=today())
    remaining = [day for day in dates if day >= today()]
    next_date = remaining[0] if remaining else upcoming_date
    upcoming, charged = series_reach(series, data.from_date or today())
    with translation.override(ctx.language):
        label = series_label(series)
    return {
        **series_out(series),
        "next_date": next_date,
        "upcoming": upcoming,
        "charged": charged,
        "label": label,
    }
