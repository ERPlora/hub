"""The states of an appointment (APPOINTMENT-F03, F05, F07, F08, F09): confirmed, in progress, completed, no-show and
cancelled.
"""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, PermissionDenied
from live.operations import operation

from apps.appointment import events
from apps.appointment.queries import (
    CHANGE_ALL,
    CHANGE_OWN,
    MOVABLE,
    by_person,
    current_settings,
    find_appointment,
    load_detail,
    may_change,
    now,
)
from apps.appointment.schemas import AppointmentOut, AppointmentRefIn, CancelIn
from apps.appointment.services.moving import _acting_for_customer
from apps.appointment.services.writes import (
    CANNOT,
    CHANGE_OWN_ONLY,
    A,
    S,
    _actor,
    _event,
    _history,
    _refuse_with_open_check,
)

NO_SHOW_TOO_EARLY = _(
    "It is not the appointment's time yet: it cannot be marked as a no-show."
)
CANCELLATION_DISABLED = _(
    "Online cancellation is not available. Please contact the business."
)
CANCELLATION_NOTICE = _(
    "This appointment can only be cancelled online %(hours)s hours ahead. Please contact the business."
)


def _transition(  # noqa: PLR0913
    ctx: OperationContext,
    data: AppointmentRefIn,
    *,
    allowed: tuple,
    to: str,
    action: str,
    event: str,
    cannot: str,
) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if appointment.status not in allowed:
        raise Conflict(str(CANNOT[cannot]), code=f"appointment.cannot_{cannot}")
    appointment.status = to
    appointment.updated_by = _actor(ctx)
    appointment.save(update_fields=["status", "updated_by", "updated_at"])
    _history(ctx, appointment, action)
    _event(ctx, event, appointment)
    return load_detail(ctx, appointment.id)


@operation(
    "appointment.appointment.confirm",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "confirm Teresa's pending appointment",
                "accept the appointment Paula is waiting on",
            ),
            "es": (
                "da por buena la cita pendiente de Teresa",
                "acepta la cita que tiene pendiente Paula",
            ),
        },
        "description": "Confirm a pending appointment (a booking the customer made, waiting for review).",
        "risk": "normal",
    },
)
def confirm(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.PENDING,),
        to=S.CONFIRMED,
        action=A.CONFIRMED,
        event=events.APPOINTMENT_CONFIRMED,
        cannot="confirm",
    )


@operation(
    "appointment.appointment.start",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Clara is here, start her appointment",
                "Sara just walked in for her 10 o'clock",
            ),
            "es": (
                "ya está aquí Clara, empieza su cita",
                "ha llegado Sara a su cita de las 10:00, ponla en curso",
            ),
        },
        "description": "The customer arrived: start the service of a pending or confirmed appointment.",
        "risk": "normal",
    },
)
def start(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.PENDING, S.CONFIRMED),
        to=S.IN_PROGRESS,
        action=A.STARTED,
        event=events.APPOINTMENT_STARTED,
        cannot="start",
    )


@operation(
    "appointment.appointment.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Julia's appointment is finished",
                "mark Pilar's appointment as completed",
            ),
            "es": (
                "ya hemos acabado con la cita de Julia",
                "da por completada la cita de Pilar",
                "ya está prestado el tinte de Clara, da su cita por acabada",
            ),
        },
        "description": "Complete an appointment in progress (or confirmed). Charging it also completes it.",
        "risk": "normal",
    },
)
def complete(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.CONFIRMED, S.IN_PROGRESS),
        to=S.COMPLETED,
        action=A.COMPLETED,
        event=events.APPOINTMENT_COMPLETED,
        cannot="complete",
    )


@operation(
    "appointment.appointment.mark_no_show",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Inés never showed up for her appointment",
                "mark Carmen's appointment as a no-show",
            ),
            "es": (
                "Inés no vino a su cita",
                "apunta que Carmen faltó a la cita de ayer",
                "Beatriz no se ha presentado a su cita de las 12:00",
            ),
        },
        "description": "Record that the customer did not show up, once the appointment's time has passed (pending or "
        "confirmed, not charged).",
        "risk": "high",
    },
)
def mark_no_show(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number)
    _refuse_with_open_check(appointment)
    if (
        appointment.status in MOVABLE
        and not appointment.sale_id
        and appointment.start > now()
    ):
        raise Conflict(str(NO_SHOW_TOO_EARLY), code="appointment.no_show_too_early")
    allowed = (S.PENDING, S.CONFIRMED) if not appointment.sale_id else ()
    return _transition(
        ctx,
        data,
        allowed=allowed,
        to=S.NO_SHOW,
        action=A.NO_SHOW,
        event=events.APPOINTMENT_MARKED_NO_SHOW,
        cannot="mark_no_show",
    )


@operation(
    "appointment.appointment.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=CancelIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel Beatriz's appointment on Friday",
                "Sara can't make it, call off her appointment",
            ),
            "es": (
                "anula la cita del viernes de Beatriz",
                "a Sara le ha surgido algo, cancela su cita del jueves",
            ),
        },
        "description": "Cancel an appointment (pending, confirmed or no-show; not a charged one), with an optional "
        "reason; its time becomes free. on_behalf_of_customer=true (with the customer) when she cancels herself: it "
        "must be hers and the business's cancellation policy applies.",
        "risk": "high",
        # An automation cancels anybody's (``is_own``), so a yes to it is only of someone who may too (FLOW-F28).
        "yes_permission": CHANGE_ALL,
    },
)
def cancel(ctx: OperationContext, data: CancelIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    by_customer = _acting_for_customer(ctx, appointment, data)
    if (
        appointment.status not in (S.PENDING, S.CONFIRMED, S.NO_SHOW)
        or appointment.sale_id
    ):
        raise Conflict(str(CANNOT["cancel"]), code="appointment.cannot_cancel")
    _refuse_with_open_check(appointment)
    if by_customer or not by_person(ctx):
        settings = current_settings()
        if not settings.allow_customer_cancellation:
            raise Conflict(
                str(CANCELLATION_DISABLED),
                code="appointment.customer_cancellation_disabled",
            )
        if appointment.start - now() < dt.timedelta(
            hours=settings.cancellation_notice_hours
        ):
            raise Conflict(
                str(CANCELLATION_NOTICE)
                % {"hours": settings.cancellation_notice_hours},
                code="appointment.cancellation_notice_required",
            )
    appointment.status = S.CANCELLED
    appointment.cancelled_at = timezone.now()
    appointment.cancellation_reason = data.reason
    appointment.cancelled_by_customer = by_customer
    appointment.updated_by = _actor(ctx)
    appointment.save()
    _history(ctx, appointment, A.CANCELLED, by_customer=by_customer, reason=data.reason)
    _event(ctx, events.APPOINTMENT_CANCELLED, appointment, by_customer=by_customer)
    return load_detail(ctx, appointment.id)
