"""Changing a repeating appointment from one of its dates on (APPOINTMENT-F14): this one and all that follow."""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.appointment import assistant_cards
from apps.appointment import engine, events
from apps.appointment.models import Appointment, Recurring, RecurringService
from apps.appointment.queries.access import CHANGE_OWN, may_change
from apps.appointment.queries.agenda import verdict_message
from apps.appointment.queries.booking import check_member, lines_for, resolve_services
from apps.appointment.queries.business import now
from apps.appointment.queries.reads import MOVABLE
from apps.appointment.queries.series import find_series, load_series, pattern_of
from apps.appointment.schemas import (
    END_BEFORE_START,
    RecurringUpdatedOut,
    RecurringUpdateIn,
)
from apps.appointment.services.moving import _move
from apps.appointment.services.series import (
    RECURRING_NO_STAFF,
    _book_window,
    _series_services,
)
from apps.appointment.services.writes import (
    CHANGE_OWN_ONLY,
    A,
    S,
    _actor,
    _event,
    _history,
    lock_appointments,
)
from apps.staff.queries import resolve_member
from base.business import business_zone

PATTERN_CHANGED = _("The repeating appointment changed its pattern")


@operation(
    "appointment.recurring.update",
    kind="command",
    permission=CHANGE_OWN,
    input=RecurringUpdateIn,
    output=RecurringUpdatedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "from next week, move Teresa's repeating appointment to Wednesdays",
                "change Carmen's weekly appointment to 11 am from now on",
            ),
            "es": (
                "desde la semana que viene, la cita fija de Teresa pasa a los miércoles",
                "cambia la cita fija de Carmen a las 11:00 de aquí en adelante",
            ),
        },
        "description": "Edit a repeating appointment from one of its dates on (this and all following): its time, "
        "length, repetition, weekday, professional (by name) or services. Before that date nothing changes (the series "
        "is split); appointments already charged, in progress or completed are left alone; the booked ones that still "
        "fall on the pattern move, the others are cancelled, and the ones that do not fit stay and are listed.",
        "risk": "normal",
        "summary": assistant_cards.series_change,
    },
)
def update_series(ctx: OperationContext, data: RecurringUpdateIn) -> dict:  # noqa: C901, PLR0912, PLR0915
    series = find_series(ctx, data.id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    sent = data.model_fields_set
    # The last date can be neither before the change (a split starts there) nor before the series starts.
    if data.end_date is not None and data.end_date < max(
        data.from_date, series.start_date
    ):
        message = str(END_BEFORE_START)
        raise InvalidPayload(message, fields={"end_date": message})
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else series.staff
    )
    if member is not None and member != series.staff and not may_change(ctx, member.id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    services = (
        resolve_services(data.services) if data.services else _series_services(series)
    )
    if member is not None:
        check_member(member, services)
    frequency = data.frequency or series.frequency
    weekly = frequency in ("weekly", "biweekly")
    day_of_week = data.day_of_week if "day_of_week" in sent else series.day_of_week
    if weekly and day_of_week is None:
        day_of_week = data.from_date.weekday()
    rule = {
        "frequency": frequency,
        "day_of_week": day_of_week if weekly else None,
        "time": (data.time or series.time).replace(second=0, microsecond=0),
        "duration_minutes": data.duration_minutes
        or (
            sum(line["duration_minutes"] for line in lines_for(member, services))
            if data.services
            else series.duration_minutes
        ),
        "end_date": data.end_date if "end_date" in sent else series.end_date,
        "staff": member,
        "staff_name": member.full_name if member else "",
    }
    old_pattern = pattern_of(series)
    # A pause stays (by hand, or the customer's data erased); only a series that lost its professional
    # (Staff's termination) comes back once it gets one.
    active = (series.is_active or series.staff is None) and member is not None
    if data.from_date <= engine.first_date(old_pattern):
        target = series
        for field, value in rule.items():
            setattr(target, field, value)
        if "max_occurrences" in sent:
            target.max_occurrences = data.max_occurrences
        target.is_active = active
        target.save()
    else:
        before = engine.count_before(old_pattern, data.from_date)
        remaining = (
            data.max_occurrences
            if "max_occurrences" in sent
            else (
                max(series.max_occurrences - before, 1)
                if series.max_occurrences
                else None
            )
        )
        series.end_date = data.from_date - dt.timedelta(days=1)
        series.save(update_fields=["end_date", "updated_at"])
        target = Recurring.objects.create(
            customer=series.customer,
            customer_name=series.customer_name,
            start_date=data.from_date,
            max_occurrences=remaining,
            split_from=series,
            is_active=active,
            created_by=_actor(ctx),
            **rule,
        )
    if data.services or target is not series:
        target.lines.all().delete()
        RecurringService.objects.bulk_create(
            RecurringService(recurring=target, service=service, position=position)
            for position, service in enumerate(services)
        )
    new_pattern = pattern_of(target)
    outcome = {"moved": 0, "cancelled": 0, "locked": 0, "skipped": [], "booked": 0}
    affected = Appointment.objects.filter(
        recurring=series, deleted_at__isnull=True, occurrence_date__gte=data.from_date
    )
    locked = lock_appointments(affected.values_list("id", flat=True))
    affected = affected.filter(pk__in=locked).order_by("occurrence_date")
    moment = now()
    zone = business_zone()
    for appointment in affected:
        in_pattern = engine.contains(new_pattern, appointment.occurrence_date)
        if (
            appointment.status in (S.IN_PROGRESS, S.COMPLETED)
            or appointment.sale_id
            or appointment.order_id
        ):
            outcome["locked"] += 1
        elif appointment.status in MOVABLE and appointment.start >= moment:
            if not in_pattern:
                appointment.status = S.CANCELLED
                appointment.cancelled_at = timezone.now()
                appointment.cancellation_reason = str(PATTERN_CHANGED)
                # Its date is no longer one of the series: a pattern changed back books it again.
                appointment.occurrence_date = None
                appointment.save()
                _history(ctx, appointment, A.CANCELLED, reason=str(PATTERN_CHANGED))
                _event(
                    ctx, events.APPOINTMENT_CANCELLED, appointment, by_customer=False
                )
                outcome["cancelled"] += 1
                continue
            code = None
            if member is None:
                code = "no_staff"
            else:
                try:
                    when = engine.aware(
                        dt.datetime.combine(appointment.occurrence_date, target.time),
                        zone,
                    )
                    if _move(
                        ctx,
                        appointment,
                        start=when,
                        minutes=target.duration_minutes,
                        staff_id=member.id,
                        staff=None,
                        service_refs=data.services,
                        by_customer=False,
                        reason="",
                        confirm_overlap=False,
                        strict=True,
                    ):
                        outcome["moved"] += 1
                except engine.NonexistentTime:
                    code = "invalid_start"
                except Conflict as refusal:
                    code = refusal.code.removeprefix("appointment.")
                    code = "overlap" if code == "slot_taken" else code
            if code:
                message = (
                    str(RECURRING_NO_STAFF)
                    if code == "no_staff"
                    else verdict_message(code)
                )
                outcome["skipped"].append(
                    {
                        "occurrence_date": appointment.occurrence_date,
                        "code": code,
                        "message": message,
                    }
                )
        if in_pattern and appointment.recurring_id != target.id:
            appointment.recurring = target
            appointment.save(update_fields=["recurring", "updated_at"])
    record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
    if target is not series:
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(target.id)})
    if target.is_active:
        outcome["booked"] = _book_window(ctx, target, from_date=data.from_date)[
            "booked"
        ]
    return {"recurring": load_series(target.id), **outcome}
