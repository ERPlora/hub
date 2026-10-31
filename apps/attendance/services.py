"""Write operations of the attendance app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). Every write on a
person's working days locks that person's staff record first (``FOR NO KEY UPDATE``, which never holds
up Staff's own writes on it), so two taps at once, or a correction against a clock-in, wait for each
other and decide on what the first one left. The partial unique indexes (one open day per person, one
running break per day) still hold whatever door writes; hitting one is turned into the same 409.
Times are the server's (``timezone.now()``); the distance to the workplace is measured here.
"""

import datetime as dt
from typing import Any

from django.db import IntegrityError
from django.db.models import Case, DateTimeField, F, Value, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from geopy.distance import geodesic
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import atomic, operation
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from apps.attendance.queries import (
    MEMBER_NOT_FOUND,
    RECORD_NOT_FOUND,
    TERMINATED_REASON_SOURCE,
    business_date,
    find_member,
    is_stale,
    load_record,
    own_member,
    review_hours,
    saved_settings,
    settings_values,
    user_name,
)
from apps.attendance.schemas import (
    BOTH_COORDINATES,
    BreakIn,
    ClockInIn,
    ClockOutIn,
    ClosedOut,
    CorrectIn,
    EmptyIn,
    MemberRefIn,
    PositionIn,
    RecordOut,
    ReviewOut,
    SettingsIn,
    SettingsOut,
    TerminatedIn,
)
from apps.staff.models import Member
from base.services import acting_hub_user

NO_MEMBER_RECORD = _(
    "Your user is not linked to any staff record: ask a manager to link it in Staff."
)
OTHERS_DENIED = _("You can only clock yourself in and out.")
MEMBER_NOT_ACTIVE = _(
    "That staff record is not active (inactive or on leave), so it cannot clock in."
)
ALREADY_IN = _(
    "You already have an open working day: clock out before clocking in again."
)
ALREADY_IN_OTHER = _(
    "%(name)s already has an open working day: clock them out before clocking in again."
)
NOT_CLOCKED_IN = _("There is no open working day: clock in first.")
BREAK_RUNNING = _("A break is already running.")
NO_BREAK_RUNNING = _("There is no running break to end.")
LOCATION_REQUIRED = _(
    "Your location is needed to clock in from this device. Allow it, or clock in at the counter."
)
WORKPLACE_NOT_SET = _(
    "The workplace location is not set yet, so this device cannot clock in. Ask a manager to set it in "
    "the time clock settings, or clock in at the counter."
)
OUTSIDE_RADIUS = _(
    "You are %(distance)s m from the workplace, outside the allowed %(radius)s m. Move closer to clock "
    "in, or clock in at the counter."
)
OVERLAP = _("These hours overlap another working day of this person.")
SECOND_OPEN_DAY = _(
    "That person already has another open working day: this one cannot be reopened."
)
IN_THE_FUTURE = _("The time cannot be in the future.")
DAY_NEEDS_REVIEW = _(
    "This working day has been open more than %(hours)s hours and is waiting for review: a manager "
    "corrects it. Clock in to start a new day."
)

CLOCK_OTHERS = "attendance.clock_others"
#: A clock-out never lands on its own clock-in (the database keeps «after»): the smallest step after it.
TICK = dt.timedelta(microseconds=1)


# ── Who and where ───────────────────────────────────────────────────────────────────────────────


def _target(ctx: OperationContext, data: MemberRefIn) -> tuple[Member, bool]:
    """The staff record the command acts on, locked, and whether it is the caller's own.

    None named: the caller's own (409 ``attendance.no_member_record`` without one). Someone else needs
    ``attendance.clock_others``. A record terminated meanwhile is ``NotFound``.
    """
    own = own_member(ctx)
    if data.member_id is not None or data.member:
        member = find_member(data.member_id, data.member)
        mine = own is not None and member.pk == own.pk
        if not mine and not ctx.has(CLOCK_OTHERS):
            raise PermissionDenied(str(OTHERS_DENIED))
    elif own is None:
        raise Conflict(str(NO_MEMBER_RECORD), code="attendance.no_member_record")
    else:
        member, mine = own, True
    locked = (
        Member.objects.select_for_update(no_key=True)
        .filter(pk=member.pk)
        .exclude(status=Member.Status.TERMINATED)
        .first()
    )
    if locked is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return locked, mine


def _open_day(member: Member) -> Record | None:
    return Record.objects.filter(member=member, status=Record.Status.OPEN).first()


def _day_now(member: Member, now: dt.datetime) -> Record | None:
    """The person's open day to clock out of or pause; a forgotten one (past the review hours) is not.

    A forgotten day is never closed as a 20-hour day nor paused: 409 ``attendance.day_needs_review``,
    and a manager corrects it (ATTENDANCE-F05, F08). Clocking in again flags it and opens a new day.
    """
    record = _open_day(member)
    hours = review_hours()
    if record is not None and is_stale(record, hours, now):
        raise Conflict(
            str(DAY_NEEDS_REVIEW) % {"hours": hours}, code="attendance.day_needs_review"
        )
    return record


def _not_clocked_in() -> Conflict:
    return Conflict(str(NOT_CLOCKED_IN), code="attendance.not_clocked_in")


def device_source(ctx: OperationContext) -> str:
    """The device that clocks: the counter POS (``shared``) or someone's own phone (``personal``).

    It is the platform's to say, never the payload's: phase 2 reads it from the session's trusted
    device (`base`, with the PIN). Phase 1 has no device modes, so every device clocks as the shared one,
    the strict fallback of the old module: the location is never asked for (ATTENDANCE-F03).
    """
    return Record.Source.SHARED


def _measure(values: dict, data: PositionIn, source: str) -> dict[str, Any]:
    """What is kept of where the device is (ATTENDANCE-F03; review of 2026-10-15, finding 7).

    With the workplace set, the distance the Hub measures, inside/outside and the accuracy. The exact
    coordinates only when the business requires the location and the device is personal: nobody asked
    for them otherwise, and the day keeps them as long as the record (four years, art. 34.9 ET).
    """
    has_position = data.lat is not None and data.lng is not None
    distance = within = None
    if has_position and values["workplace_set"]:
        distance = geodesic((values["workplace_lat"], values["workplace_lng"]), (data.lat, data.lng)).meters
        within = distance <= values["geofence_radius_m"]
        distance = round(distance, 1)
    keep = has_position and values["require_location"] and source == Record.Source.PERSONAL
    return {
        "lat": data.lat if keep else None,
        "lng": data.lng if keep else None,
        "accuracy_m": data.accuracy_m if has_position else None,
        "distance_m": distance,
        "within_radius": within,
    }


def _check_radius(values: dict, source: str, where: dict[str, Any]) -> None:
    """ATTENDANCE-F03: a personal device must be within the radius when the business asks for it."""
    if not values["require_location"] or source != Record.Source.PERSONAL:
        return
    if not values["workplace_set"]:
        raise Conflict(str(WORKPLACE_NOT_SET), code="attendance.workplace_not_set")
    if where["distance_m"] is None:
        raise Conflict(str(LOCATION_REQUIRED), code="attendance.location_required")
    if not where["within_radius"]:
        raise Conflict(
            str(OUTSIDE_RADIUS) % {"distance": round(where["distance_m"]), "radius": values["geofence_radius_m"]},
            code="attendance.outside_radius",
        )


def _flag_stale(ctx: OperationContext, days, hours: int, now: dt.datetime) -> list:
    """ATTENDANCE-F05: the open days older than ``hours`` wait for review; nobody invents a clock-out."""
    flagged = []
    limit = now - dt.timedelta(hours=hours)
    for record in days.filter(
        status=Record.Status.OPEN, clock_in_at__lt=limit
    ).order_by("clock_in_at", "id"):
        # Only what is still open when the UPDATE runs: a clock-out meanwhile wins.
        updated = Record.objects.filter(pk=record.pk, status=Record.Status.OPEN).update(
            status=Record.Status.NEEDS_REVIEW, updated_at=now
        )
        if updated:
            record_event(
                ctx,
                events.RECORD_FLAGGED,
                {"id": str(record.id), "member_id": str(record.member_id)},
            )
            flagged.append(record.id)
    return flagged


def _end_break(ctx: OperationContext, record: Record, at: dt.datetime) -> bool:
    running = Break.objects.filter(record=record, ended_at__isnull=True).first()
    if running is None:
        return False
    running.ended_at = max(at, running.started_at)
    running.save(update_fields=["ended_at", "updated_at"])
    record_event(
        ctx,
        events.BREAK_ENDED,
        {
            "id": str(running.id),
            "record_id": str(record.id),
            "member_id": str(record.member_id),
        },
    )
    return True


# ── Clocking (ATTENDANCE-F01, F02, F03, F12) ────────────────────────────────────────────────────


@operation(
    "attendance.record.clock_in",
    kind="command",
    permission="attendance.clock",
    input=ClockInIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "Clocks in («clock me in», «ficha la entrada de Ana»): opens the working day of the "
        "caller, or of the person named, at the server's time. Refused when the person already has an "
        "open day or, from a personal device, when it is outside the workplace radius.",
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
    where = _measure(values, data, source)
    _check_radius(values, source, where)
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
    permission="attendance.clock",
    input=ClockOutIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "Clocks out («clock me out», «ficha la salida de Ana»): closes the open working day "
        "of the caller, or of the person named, at the server's time, ending the running break. Never "
        "blocked by the location.",
        "risk": "normal",
    },
)
def clock_out(ctx: OperationContext, data: ClockOutIn) -> dict:
    member, _mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None:
        raise _not_clocked_in()
    out = now if now > record.clock_in_at else record.clock_in_at + TICK
    _end_break(ctx, record, out)
    where = _measure(settings_values(saved_settings()), data, record.source)
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


@operation(
    "attendance.break.start",
    kind="command",
    permission="attendance.clock",
    input=BreakIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "Starts a break inside the open working day of the caller, or of the person named "
        "(«I'm going on a break»).",
        "risk": "normal",
    },
)
def start_break(ctx: OperationContext, data: BreakIn) -> dict:
    member, _mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None:
        raise _not_clocked_in()
    running = Conflict(str(BREAK_RUNNING), code="attendance.break_running")
    if Break.objects.filter(record=record, ended_at__isnull=True).exists():
        raise running
    try:
        with atomic():
            pause = Break.objects.create(
                record=record, started_at=max(now, record.clock_in_at)
            )
    except IntegrityError:
        raise running from None
    record_event(
        ctx,
        events.BREAK_STARTED,
        {"id": str(pause.id), "record_id": str(record.id), "member_id": str(member.id)},
    )
    return load_record(record.id, now)


@operation(
    "attendance.break.end",
    kind="command",
    permission="attendance.clock",
    input=BreakIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "Ends the running break of the caller, or of the person named («I'm back»).",
        "risk": "normal",
    },
)
def end_break(ctx: OperationContext, data: BreakIn) -> dict:
    member, _mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None or not _end_break(ctx, record, now):
        raise Conflict(str(NO_BREAK_RUNNING), code="attendance.no_break_running")
    return load_record(record.id, now)


# ── Corrections (ATTENDANCE-F08) ────────────────────────────────────────────────────────────────


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
    permission="attendance.correct",
    input=CorrectIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "Corrects the clock-in and clock-out of a working day with a mandatory reason (the "
        "day's history keeps the before, the after, the reason and who). Without a clock-out the day is "
        "open again. Refused when the hours overlap another day of the same person. This rewrites the "
        "legal working-day record: confirm the times and the reason first.",
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


# ── Settings (ATTENDANCE-F04) ───────────────────────────────────────────────────────────────────

#: Settings that cannot be empty: a ``null`` leaves them as they are.
REQUIRED_SETTINGS = ("require_location", "geofence_radius_m", "auto_close_after_hours")


@operation(
    "attendance.settings.update",
    kind="command",
    permission="attendance.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Changes the time clock settings (only the fields sent): whether a personal device "
        "must be within the workplace radius to clock in, the radius, the workplace coordinates and after "
        "how many hours a forgotten day is flagged for review.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    row, created = AttendanceSettings.objects.get_or_create(slot=1)
    row = AttendanceSettings.objects.select_for_update().get(pk=row.pk)
    changed = created
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field in REQUIRED_SETTINGS:
            continue
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    if (row.workplace_lat is None) != (row.workplace_lng is None):
        missing = "workplace_lat" if row.workplace_lat is None else "workplace_lng"
        raise InvalidPayload(
            str(BOTH_COORDINATES), fields={missing: str(BOTH_COORDINATES)}
        )
    if changed:
        row.updated_by = acting_hub_user(ctx)
        row.save()
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_values(row)


# ── The system (ATTENDANCE-F05, F13) ────────────────────────────────────────────────────────────


@operation(
    "attendance.record.review_stale",
    kind="command",
    permission="attendance.correct",
    input=EmptyIn,
    output=ReviewOut,
    ai={
        "description": "Flags for review every working day still open after the hours of the settings "
        "(a forgotten clock-out). It never invents a clock-out. The scheduled task runs it every 15 minutes.",
        "risk": "normal",
    },
)
def review_stale(ctx: OperationContext, data: EmptyIn) -> dict:
    hours = settings_values(saved_settings())["auto_close_after_hours"]
    flagged = _flag_stale(ctx, Record.objects.all(), hours, timezone.now())
    return {"flagged": len(flagged), "record_ids": flagged}


@operation(
    "attendance.record.close_for_terminated",
    kind="command",
    permission="attendance.correct",
    input=TerminatedIn,
    output=ClosedOut,
    ai={
        "description": "Closes, at this moment and with a correction of the system, the open working day of "
        "a staff member who was terminated in Staff (its reaction to staff.member.terminated).",
        "risk": "normal",
    },
)
def close_for_terminated(ctx: OperationContext, data: TerminatedIn) -> dict:
    # Only a terminated record: a stray or replayed call for anyone else changes nothing.
    member = (
        Member.objects.select_for_update(no_key=True)
        .filter(pk=data.id, status=Member.Status.TERMINATED)
        .first()
    )
    record = _open_day(member) if member is not None else None
    if record is None:
        return {"record": None}
    record = Record.objects.select_for_update().get(pk=record.pk)
    now = timezone.now()
    out = now if now > record.clock_in_at else record.clock_in_at + TICK
    _end_break(ctx, record, out)
    _correct(ctx, record, record.clock_in_at, out, TERMINATED_REASON_SOURCE)
    return {"record": load_record(record.id, now)}
