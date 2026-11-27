"""References by id, name or date (the assistant speaks): the special day or the temporary change a command names,
and the two reads by id that name them on the card of a write."""

import datetime as dt
from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation

from apps.schedule.models import Override, SpecialDay
from apps.schedule.schemas.fields import ByIdIn
from apps.schedule.schemas.overrides import OverrideOut
from apps.schedule.schemas.special_days import SpecialDayOut
from base.text_search import contains_text

from .outputs import override_out, special_day_out

SPECIAL_DAY_NOT_FOUND = _("That special day does not exist in this business.")
OVERRIDE_NOT_FOUND = _("That temporary change does not exist in this business.")
AMBIGUOUS = _("There are several with “%(name)s”: %(matches)s. Say which one.")
MAX_CANDIDATES = 5


def _as_date(text: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _by_text(rows: QuerySet[Any], field: str, text: str, label: Any) -> Any:
    """The row whose ``field`` is ``text`` (any case), else the one that contains it; 409 if several."""
    matches = list(
        rows.filter(**{f"{field}__iexact": text})[: MAX_CANDIDATES + 1]
    ) or list(rows.filter(contains_text(text, field))[: MAX_CANDIDATES + 1])
    if len(matches) > 1:
        names = ", ".join(str(match) for match in matches[:MAX_CANDIDATES])
        raise Conflict(
            str(AMBIGUOUS) % {"name": text, "matches": names},
            code="schedule.ambiguous_reference",
        )
    if not matches:
        raise NotFound(str(label))
    return matches[0]


def resolve_special_day(
    special_day_id: UUID | None, text: str | None, *, lock: bool = False
) -> SpecialDay:
    """The special day by id; or by date (a yearly one answers for its day and month of any year); or
    by name. ``lock`` takes its row until the end of the command."""
    rows = SpecialDay.objects.select_for_update() if lock else SpecialDay.objects.all()
    if special_day_id is not None:
        found = rows.filter(pk=special_day_id).first()
        if found is None:
            raise NotFound(str(SPECIAL_DAY_NOT_FOUND))
        return found
    on = _as_date(text or "")
    if on is None:
        return _by_text(
            rows.order_by("date", "id"), "name", text or "", SPECIAL_DAY_NOT_FOUND
        )
    found = rows.filter(date=on).first() or (
        rows.filter(recurring_yearly=True, date__month=on.month, date__day=on.day)
        .order_by("-date", "-id")
        .first()
    )
    if found is None:
        raise NotFound(str(SPECIAL_DAY_NOT_FOUND))
    return found


def resolve_override(
    override_id: UUID | None, text: str | None, *, lock: bool = False
) -> Override:
    """The temporary change by id; or the one covering a date; or by reason."""
    rows = Override.objects.select_for_update() if lock else Override.objects.all()
    if override_id is not None:
        found = rows.filter(pk=override_id).first()
        if found is None:
            raise NotFound(str(OVERRIDE_NOT_FOUND))
        return found
    on = _as_date(text or "")
    if on is None:
        return _by_text(
            rows.order_by("start_date", "id"), "reason", text or "", OVERRIDE_NOT_FOUND
        )
    found = (
        rows.filter(start_date__lte=on, end_date__gte=on)
        .order_by("-start_date", "-id")
        .first()
    )
    if found is None:
        raise NotFound(str(OVERRIDE_NOT_FOUND))
    return found


# Not assistant tools: what names a special day or a temporary change on the card of a write (``schemas.fields.A_SPECIAL_DAY``,
# ``A_OVERRIDE``), as their list shows them; the model finds them in their lists.
@operation(
    "schedule.special_day.get",
    kind="query",
    permission="schedule.view",
    input=ByIdIn,
    output=SpecialDayOut,
    ai=INTERNAL,
)
def get_special_day(ctx: OperationContext, data: ByIdIn) -> dict:
    return special_day_out(resolve_special_day(data.id, None))


@operation(
    "schedule.override.get",
    kind="query",
    permission="schedule.view",
    input=ByIdIn,
    output=OverrideOut,
    ai=INTERNAL,
)
def get_override(ctx: OperationContext, data: ByIdIn) -> dict:
    return override_out(resolve_override(data.id, None))
