"""Temporary changes (SCHEDULE-F05, F06, F13): a range of dates closed or with other hours; two never cover the same
day."""

from django.utils import formats
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.schedule import assistant_cards, events
from apps.schedule.models import Override, OverrideInterval
from apps.schedule.queries import override_out, resolve_override
from apps.schedule.schemas.fields import RANGE_BACKWARDS, DeletedOut
from apps.schedule.schemas.overrides import OverrideIn, OverrideOut, OverridePatchIn, OverrideRefIn

from .writes import _checked, _locked_settings, _same, _stored, _write_intervals

OVERRIDE_OVERLAPS = _(
    "Those dates overlap the temporary change “%(reason)s” (%(start)s – %(end)s)."
)


def _refuse_overlap(start, end, exclude=None) -> None:
    """409 ``schedule.override_overlaps`` when a temporary change already covers a day of the range."""
    clash = (
        Override.objects.filter(start_date__lte=end, end_date__gte=start)
        .exclude(pk=exclude)
        .order_by("start_date")
        .first()
    )
    if clash is None:
        return
    message = str(OVERRIDE_OVERLAPS) % {
        "reason": clash.reason,
        "start": formats.date_format(clash.start_date, "SHORT_DATE_FORMAT"),
        "end": formats.date_format(clash.end_date, "SHORT_DATE_FORMAT"),
    }
    raise Conflict(
        message, code="schedule.override_overlaps", fields={"start_date": message}
    )


def _override_event(ctx: OperationContext, name: str, row: Override) -> None:
    record_event(
        ctx,
        name,
        {
            "id": str(row.id),
            "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(),
        },
    )


@operation(
    "schedule.override.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.add",
    input=OverrideIn,
    output=OverrideOut,
    ai={
        "description": "Adds a temporary change of the opening hours for a range of dates (holidays, summer hours, "
        "works): closed, or the same intervals every day of the range.",
        "risk": "normal", "summary": assistant_cards.override,
        "asks": {
            "en": (
                "we close from 1 to 15 August for the holidays",
                "in July and August we keep a summer timetable, 8:00 to 15:00",
            ),
            "es": (
                "añade un cierre del negocio por obras del 3 al 9 de marzo",
                "en julio y agosto hacemos horario de verano, de 8:00 a 15:00",
                "cerramos el puente de noviembre por vacaciones, del 1 al 3",
            ),
        },
    },
)
def create_override(ctx: OperationContext, data: OverrideIn) -> dict:
    """SCHEDULE-F05: two temporary changes never cover the same day."""
    _locked_settings()
    _refuse_overlap(data.start_date, data.end_date)
    row = Override.objects.create(
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        is_closed=data.is_closed,
    )
    _write_intervals(OverrideInterval, {"override": row}, data.intervals)
    _override_event(ctx, events.OVERRIDE_CREATED, row)
    return override_out(row)


@operation(
    "schedule.override.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.change",
    input=OverridePatchIn,
    output=OverrideOut,
    ai={
        "description": "Corrects a temporary change (by id, reason or a date it covers): its dates, reason, closed or "
        "hours; only what is sent changes, and sent intervals replace them all.",
        "risk": "normal",
        "asks": {
            "en": (
                "the summer holidays end on the 20th, not on the 15th",
                "make the summer opening last until the end of September",
            ),
            "es": (
                "las vacaciones de verano acaban el 20 y no el 15",
                "alarga la apertura de verano hasta finales de septiembre",
                "corrige las fechas de las obras: empiezan el lunes 3",
            ),
        },
    },
)
def update_override(ctx: OperationContext, data: OverridePatchIn) -> dict:
    """SCHEDULE-F13; no change, no event."""
    _locked_settings()
    row = resolve_override(data.id, data.override, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude={"id", "override", "intervals"})
    before = _stored(row)
    fields_changed = False
    for field, value in sent.items():
        if value is not None and getattr(row, field) != value:
            setattr(row, field, value)
            fields_changed = True
    if row.end_date < row.start_date:
        raise InvalidPayload(
            str(RANGE_BACKWARDS), fields={"end_date": str(RANGE_BACKWARDS)}
        )
    intervals = data.intervals if data.intervals is not None else before
    if data.intervals is not None and row.is_closed and "is_closed" not in sent:
        row.is_closed = False
        fields_changed = True
    after = _checked(row.is_closed, intervals)
    if fields_changed:
        _refuse_overlap(row.start_date, row.end_date, exclude=row.pk)
        row.save()
    if not _same(before, after):
        _write_intervals(OverrideInterval, {"override": row}, after)
    if fields_changed or not _same(before, after):
        _override_event(ctx, events.OVERRIDE_UPDATED, row)
    return override_out(row)


@operation(
    "schedule.override.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.delete",
    input=OverrideRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a temporary change (by id, reason or a date it covers) and its hours; the usual week "
        "rules those dates again. Cannot be undone.",
        "risk": "high",
        "asks": {
            "en": (
                "cancel the summer closure, this year we stay open",
                "drop the summer opening and go back to normal",
            ),
            "es": (
                "quita el cierre de vacaciones, este verano abrimos",
                "anula la apertura de verano y vuelve a lo de siempre",
            ),
        },
    },
)
def delete_override(ctx: OperationContext, data: OverrideRefIn) -> dict:
    """SCHEDULE-F06."""
    row = resolve_override(data.id, data.override, lock=True)
    deleted = row.id
    row.delete()
    record_event(ctx, events.OVERRIDE_DELETED, {"id": str(deleted)})
    return {"id": deleted}
