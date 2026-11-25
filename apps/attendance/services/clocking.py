"""Clocking in and out: attendance.record.clock_in and .clock_out."""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import Record
from apps.attendance.queries.days import load_record
from apps.attendance.queries.reads import business_date, saved_settings, settings_values
from apps.attendance.schemas import ClockInIn, ClockOutIn, RecordOut
from apps.staff.models import Member
from base.services.sessions import acting_hub_user

from .days import TICK, _day_now, _end_break, _flag_stale, _not_clocked_in, _open_day, _target
from .location import _check_radius, _measure, device_source

MEMBER_NOT_ACTIVE = _(
    "That staff record is not active (inactive or on leave), so it cannot clock in."
)
ALREADY_IN = _(
    "You already have an open working day: clock out before clocking in again."
)
ALREADY_IN_OTHER = _(
    "%(name)s already has an open working day: clock them out before clocking in again."
)


@operation(
    "attendance.record.clock_in",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.clock",
    input=ClockInIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "clock me in",
                "clock Pedro in now",
                "I've just arrived, start my working day",
            ),
            "es": (
                "fíchame la entrada",
                "Pedro acaba de llegar, fíchalo",
                "acabo de llegar, empieza mi jornada",
            ),
        },
        "description": "Clocks in («clock me in», «ficha la entrada de Ana»): opens the working day of the "
        "caller, or of the person named, at the server's time. Refused when the person already has an "
        "open day or, from a personal device, when it is outside the workplace radius.",
        "check": "attendance.person.check",
        "risk": "normal",
    },
)
def clock_in(ctx: OperationContext, data: ClockInIn) -> dict:
    member, mine = _target(ctx, data)
    if member.status != Member.Status.ACTIVE:
        raise Conflict(str(MEMBER_NOT_ACTIVE), code="attendance.member_not_active")
    now = timezone.now()
    values = settings_values(saved_settings())
    _flag_stale(
        ctx, Record.objects.filter(member=member), values["auto_close_after_hours"], now
    )
    already = (
        Conflict(str(ALREADY_IN), code="attendance.already_clocked_in")
        if mine
        else Conflict(
            str(ALREADY_IN_OTHER) % {"name": member.full_name},
            code="attendance.already_clocked_in",
        )
    )
    if _open_day(member) is not None:
        raise already
    source = device_source(ctx)
    where = _measure(values, data, source, mine)
    _check_radius(values, source, where, mine)
    user = acting_hub_user(ctx)
    try:
        with atomic():
            record = Record.objects.create(
                member=member,
                clock_in_at=now,
                work_date=business_date(now),
                source=source,
                in_lat=where["lat"],
                in_lng=where["lng"],
                in_accuracy_m=where["accuracy_m"],
                in_distance_m=where["distance_m"],
                in_within_radius=where["within_radius"],
                created_by=user,
                updated_by=user,
            )
    except IntegrityError:
        raise already from None
    record_event(
        ctx, events.CLOCKED_IN, {"id": str(record.id), "member_id": str(member.id)}
    )
    return load_record(record.id, now)


@operation(
    "attendance.record.clock_out",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.clock",
    input=ClockOutIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "clock me out",
                "clock Pedro out now",
                "I'm leaving, end my working day",
            ),
            "es": (
                "fíchame la salida",
                "Pedro ya se ha ido, fíchale la salida",
                "me voy a casa, acaba mi jornada",
            ),
        },
        "description": "Clocks out («clock me out», «ficha la salida de Ana»): closes the open working day "
        "of the caller, or of the person named, at the server's time, ending the running break. Never "
        "blocked by the location.",
        "check": "attendance.person.check",
        "risk": "normal",
    },
)
def clock_out(ctx: OperationContext, data: ClockOutIn) -> dict:
    member, mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None:
        raise _not_clocked_in()
    out = now if now > record.clock_in_at else record.clock_in_at + TICK
    _end_break(ctx, record, out)
    where = _measure(settings_values(saved_settings()), data, device_source(ctx), mine)
    record.clock_out_at = out
    record.status = Record.Status.CLOSED
    record.out_lat = where["lat"]
    record.out_lng = where["lng"]
    record.out_accuracy_m = where["accuracy_m"]
    record.out_distance_m = where["distance_m"]
    record.out_within_radius = where["within_radius"]
    record.updated_by = acting_hub_user(ctx)
    record.save()
    record_event(
        ctx, events.CLOCKED_OUT, {"id": str(record.id), "member_id": str(member.id)}
    )
    return load_record(record.id, now)
