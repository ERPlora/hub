"""Moving and editing an appointment (APPOINTMENT-F04, F06, F22)."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import operation

from apps.appointment import engine, events
from apps.appointment.models import Appointment
from apps.appointment.queries.access import CHANGE_OWN, may_change
from apps.appointment.queries.booking import check_member, lines_for, resolve_services
from apps.appointment.queries.business import read_moment
from apps.appointment.queries.reads import APPOINTMENT_NOT_FOUND, MOVABLE, find_appointment, load_detail
from apps.appointment.schemas import AppointmentOut, RescheduleIn, UpdateIn
from apps.appointment.services.writes import (
    CANNOT,
    CHANGE_OWN_ONLY,
    A,
    _actor,
    _event,
    _history,
    _judge,
    _lock_members,
    _save_lines,
    _wall_text,
)
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country, find_customer
from apps.staff.queries import resolve_member

PHONE_INVALID = _(
    "That phone is not a valid number for the business's country. Check it, or type it with its international "
    "prefix (for example +44…)."
)


def _acting_for_customer(ctx: OperationContext, appointment: Appointment, data) -> bool:
    """Whether the customer asked. For her, the appointment must be hers (else «does not exist»); either
    way whoever writes it down may change it (acting for her never widens their own permissions)."""
    by_customer = bool(data.on_behalf_of_customer)
    if by_customer:
        asking = find_customer(ctx, data.customer_id, data.customer)
        if asking.id != appointment.customer_id:
            raise NotFound(
                str(APPOINTMENT_NOT_FOUND), code="appointment.appointment_not_found"
            )
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    return by_customer


def _move(  # noqa: C901, PLR0913
    ctx: OperationContext,
    appointment: Appointment,
    *,
    start: dt.datetime | None,
    minutes: int | None,
    staff_id: UUID | None,
    staff: str | None,
    service_refs,
    by_customer: bool,
    reason: str,
    confirm_overlap: bool,
    strict: bool = False,
) -> bool:
    """Moves ``appointment`` (time, length, professional, services) after judging it; whether anything changed.

    ``by_customer``: the customer asked (her history mark, the notice). ``strict``: judged as the customer
    would be without being her (a series edit: the notice applies and nothing overlaps).
    """
    if appointment.status not in MOVABLE or appointment.sale_id:
        raise Conflict(str(CANNOT["reschedule"]), code="appointment.cannot_reschedule")
    current = list(
        appointment.lines.select_related("service").order_by("position", "id")
    )
    old_member = appointment.staff
    member = resolve_member(staff_id, staff) if (staff_id or staff) else old_member
    services = (
        resolve_services(service_refs)
        if service_refs
        else [line.service for line in current]
    )
    handed = member is not None and member != old_member
    if handed and not may_change(ctx, member.id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    _lock_members(old_member, member)
    if member is not None and (handed or service_refs):
        check_member(member, services)
    new_lines = lines_for(member, services) if service_refs else None
    explicit_minutes = minutes is not None
    if minutes is None:
        minutes = (
            sum(line["duration_minutes"] for line in new_lines)
            if new_lines
            else appointment.duration_minutes
        )
    new_start = start or appointment.start
    new_end = engine.ends_at(new_start, minutes)
    _judge(
        ctx,
        member,
        new_start,
        new_end,
        customer=by_customer or strict,
        confirm_overlap=confirm_overlap,
        exclude=(appointment.id,),
    )
    changes = []
    # A new length that only follows new services is the services' change, not a move.
    lengthened = explicit_minutes and minutes != appointment.duration_minutes
    if new_start != appointment.start or lengthened:
        changes.append(
            (
                A.RESCHEDULED,
                {
                    "start": _wall_text(appointment.start),
                    "duration_minutes": appointment.duration_minutes,
                },
                {"start": _wall_text(new_start), "duration_minutes": minutes},
            )
        )
    if handed:
        changes.append(
            (
                A.STAFF_CHANGED,
                {"staff": appointment.staff_name},
                {"staff": member.full_name},
            )
        )
    if new_lines is not None:
        before = [(line.service_id, line.name, line.price) for line in current]
        after = [
            (line["service"].id, line["name"], line["price"]) for line in new_lines
        ]
        if before != after:
            changes.append(
                (
                    A.SERVICE_CHANGED,
                    {"services": [line.name for line in current]},
                    {
                        "services": [line["name"] for line in new_lines],
                        "duration_minutes": minutes,
                    },
                )
            )
            appointment.lines.all().delete()
            _save_lines(appointment, new_lines)
    if not changes:
        return False
    appointment.start, appointment.end, appointment.duration_minutes = (
        new_start,
        new_end,
        minutes,
    )
    if handed:
        appointment.staff, appointment.staff_name = member, member.full_name
    appointment.updated_by = _actor(ctx)
    appointment.save()
    for action, old, new in changes:
        _history(
            ctx,
            appointment,
            action,
            by_customer=by_customer,
            reason=reason,
            old=old,
            new=new,
        )
    _event(ctx, events.APPOINTMENT_RESCHEDULED, appointment)
    return True


@operation(
    "appointment.appointment.reschedule",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=RescheduleIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "move Sara's appointment to Thursday at 11",
                "push Clara's 5 pm appointment back an hour",
            ),
            "es": (
                "pasa la cita de Sara al jueves a las 11:00",
                "retrasa una hora la cita de las 17:00 de Clara",
            ),
        },
        "description": "Move an appointment (by its number or id) to another wall-clock time, change its length, hand "
        "it to another professional (by name) or change its services; only pending or confirmed, uncharged ones move. "
        "Judged like a new booking. on_behalf_of_customer=true (with the customer) when she asks herself: it must be "
        "hers and keep the notice.",
        "risk": "normal",
    },
)
def reschedule(ctx: OperationContext, data: RescheduleIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    by_customer = _acting_for_customer(ctx, appointment, data)
    _move(
        ctx,
        appointment,
        start=read_moment(data.start, "start") if data.start else None,
        minutes=data.duration_minutes,
        staff_id=data.staff_id,
        staff=data.staff,
        service_refs=data.services,
        by_customer=by_customer,
        reason=data.reason,
        confirm_overlap=data.confirm_overlap and not by_customer,
    )
    return load_detail(ctx, appointment.id)


@operation(
    "appointment.appointment.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=UpdateIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add to Lucía's appointment that she is allergic to ammonia",
                "fix the phone number on Julia's appointment",
            ),
            "es": (
                "cambia las notas de la cita de Lucía: es alérgica al amoniaco",
                "corrige el teléfono de la cita de Julia",
            ),
        },
        "description": "Edit an appointment: only what is sent changes — its notes (the visit's notes, e.g. the colour "
        "formula, in any state), the customer's phone (saved as +34…) or email on it, and, judged like a move, its "
        "time, length, professional or services.",
        "risk": "normal",
    },
)
def update_appointment(ctx: OperationContext, data: UpdateIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    sent = data.model_fields_set
    details = {}
    for field in ("notes", "internal_notes", "customer_email"):
        if field in sent:
            details[field] = getattr(data, field) or ""
    if "customer_phone" in sent:
        try:
            details["customer_phone"] = to_e164(
                data.customer_phone, business_country(ctx)
            )
        except InvalidPhone:
            message = str(PHONE_INVALID)
            raise InvalidPayload(
                message,
                code="appointment.phone_invalid",
                fields={"customer_phone": message},
            ) from None
    if sent & {"start", "duration_minutes", "staff_id", "staff", "services"}:
        _move(
            ctx,
            appointment,
            start=read_moment(data.start, "start") if data.start else None,
            minutes=data.duration_minutes,
            staff_id=data.staff_id,
            staff=data.staff,
            service_refs=data.services,
            by_customer=False,
            reason="",
            confirm_overlap=data.confirm_overlap,
        )
    changed = {
        field: value
        for field, value in details.items()
        if getattr(appointment, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(appointment, field, value)
        appointment.updated_by = _actor(ctx)
        appointment.save(update_fields=[*changed, "updated_by", "updated_at"])
        _event(ctx, events.APPOINTMENT_UPDATED, appointment)
    return load_detail(ctx, appointment.id)
