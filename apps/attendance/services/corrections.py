"""Correcting a working day, which leaves its trail: attendance.record.correct."""

import datetime as dt

from django.db import IntegrityError
from django.db.models import Case, DateTimeField, F, Value, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import Break, Correction, Record
from apps.attendance.queries.days import RECORD_NOT_FOUND, load_record
from apps.attendance.queries.reads import business_date, user_name
from apps.attendance.schemas import CorrectIn, RecordOut
from apps.staff.models import Member
from base.services.sessions import acting_hub_user

OVERLAP = _("These hours overlap another working day of this person.")
SECOND_OPEN_DAY = _(
    "That person already has another open working day: this one cannot be reopened."
)
IN_THE_FUTURE = _("The time cannot be in the future.")


def _correct(
    ctx: OperationContext,
    record: Record,
    clock_in_at: dt.datetime,
    clock_out_at: dt.datetime | None,
    reason: str,
) -> Correction:
    """Rewrites a locked day and leaves its trail; running breaks end at the new clock-out."""
    by = acting_hub_user(ctx)
    trail = Correction.objects.create(
        record=record,
        old_clock_in_at=record.clock_in_at,
        old_clock_out_at=record.clock_out_at,
        old_status=record.status,
        new_clock_in_at=clock_in_at,
        new_clock_out_at=clock_out_at,
        new_status=Record.Status.CLOSED if clock_out_at else Record.Status.OPEN,
        reason=reason,
        is_system=by is None,
        created_by=by,
        created_by_name=user_name(by),
    )
    record.clock_in_at = clock_in_at
    record.clock_out_at = clock_out_at
    record.status = trail.new_status
    record.work_date = business_date(clock_in_at)
    record.updated_by = by
    try:
        with atomic():
            record.save()
    except IntegrityError:
        raise Conflict(
            str(SECOND_OPEN_DAY), code="attendance.second_open_day"
        ) from None
    if clock_out_at is not None:
        for running in Break.objects.filter(record=record, ended_at__isnull=True):
            running.ended_at = max(clock_out_at, running.started_at)
            running.save(update_fields=["ended_at", "updated_at"])
    record_event(
        ctx,
        events.RECORD_CORRECTED,
        {
            "id": str(record.id),
            "member_id": str(record.member_id),
            "correction_id": str(trail.id),
        },
    )
    return trail


@operation(
    "attendance.record.correct",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.correct",
    input=CorrectIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "correct Javier's clock-out on Monday to 6 pm",
                "Pedro clocked in at 9 yesterday, fix his day",
                "fix Marta's wrong clock-in with the reason «forgot to clock»",
            ),
            "es": (
                "corrige la salida de Javier del lunes a las 18:00",
                "Pedro entró ayer a las 9, arregla su fichaje",
                "arregla el fichaje mal hecho de Marta con el motivo «se olvidó de fichar»",
            ),
        },
        "description": "Corrects the clock-in and clock-out of a working day with a mandatory reason (the "
        "day's history keeps the before, the after, the reason and who). Without a clock-out the day is "
        "open again. Refused when the hours overlap another day of the same person. This rewrites the "
        "legal working-day record.",
        "risk": "high",
    },
)
def correct_record(ctx: OperationContext, data: CorrectIn) -> dict:
    now = timezone.now()
    if data.clock_in_at > now:
        raise InvalidPayload(
            str(IN_THE_FUTURE), fields={"clock_in_at": str(IN_THE_FUTURE)}
        )
    if data.clock_out_at is not None and data.clock_out_at > now:
        raise InvalidPayload(
            str(IN_THE_FUTURE), fields={"clock_out_at": str(IN_THE_FUTURE)}
        )
    found = (
        Record.objects.filter(pk=data.record_id)
        .values_list("member_id", flat=True)
        .first()
    )
    if found is None:
        raise NotFound(str(RECORD_NOT_FOUND))
    Member.objects.select_for_update(no_key=True).filter(pk=found).first()
    record = Record.objects.select_for_update().get(pk=data.record_id)
    others = Record.objects.filter(member_id=record.member_id).exclude(pk=record.pk)
    if data.clock_out_at is None and others.filter(status=Record.Status.OPEN).exists():
        raise Conflict(str(SECOND_OPEN_DAY), code="attendance.second_open_day")
    # Another day runs to its clock-out, to now while open, and is only its clock-in instant while it
    # waits for review (its end is unknown). Touching is not overlapping.
    spans = others.annotate(
        ends=Case(
            When(clock_out_at__isnull=False, then=F("clock_out_at")),
            When(status=Record.Status.OPEN, then=Value(now)),
            default=F("clock_in_at"),
            output_field=DateTimeField(),
        )
    )
    if spans.filter(
        clock_in_at__lt=data.clock_out_at or now, ends__gt=data.clock_in_at
    ).exists():
        raise Conflict(str(OVERLAP), code="attendance.overlap")
    _correct(ctx, record, data.clock_in_at, data.clock_out_at, data.reason)
    return load_record(record.id, now)
