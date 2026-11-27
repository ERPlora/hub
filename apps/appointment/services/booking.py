"""Booking (APPOINTMENT-F01, F18, F21): one appointment, or several at once."""

from dataclasses import replace

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.appointment import assistant_cards
from apps.appointment import engine
from apps.appointment.models.appointments import Appointment
from apps.appointment.queries.access import ADD_OWN
from apps.appointment.queries.agenda import load_agenda
from apps.appointment.queries.business import current_settings, read_moment
from apps.appointment.queries.reads import CUSTOMER_SOURCES, load_detail
from apps.appointment.schemas.appointments import AppointmentOut, AppointmentsOut
from apps.appointment.schemas.booking import AppointmentCreateIn, BulkCreateIn
from apps.appointment.services.writes import _booking_basis, _create, _judge, _short
from base.business import business_zone

BATCH_AT = _("%(time)s: %(reason)s")


@operation(
    "appointment.appointment.create",
    kind="command",
    permission=ADD_OWN,
    input=AppointmentCreateIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "make an appointment for Lucía on Friday at 5 pm with Inés for a colour",
                "put Julia down for an appointment tomorrow at 10",
            ),
            "es": (
                "dale cita a Lucía el viernes a las 17:00 para un tinte con Inés",
                "crea una cita para Julia mañana a las 10:00",
            ),
        },
        "description": "Book an appointment: a customer (by name, phone or email), one or more services (by name) and a "
        "professional (by name) at a wall-clock time of the business (e.g. tomorrow at 10:00 with Ana for a haircut). "
        "Names, prices and lengths are frozen from the catalog. It is refused with its reason when the business is "
        "shut, the professional does not work then or is off, the time is blocked, or too far ahead; when it overlaps "
        "another appointment of the professional, ask the person and send confirm_overlap=true to book anyway. "
        "source=online or whatsapp when the customer books herself.",
        "risk": "normal",
        "summary": assistant_cards.booking,
    },
)
def create_appointment(ctx: OperationContext, data: AppointmentCreateIn) -> dict:
    customer, member, lines, minutes = _booking_basis(ctx, data)
    start = read_moment(data.start, "start")
    by_customer = data.source in CUSTOMER_SOURCES
    _judge(
        ctx,
        member,
        start,
        engine.ends_at(start, minutes),
        customer=by_customer,
        confirm_overlap=data.confirm_overlap,
    )
    appointment = _create(
        ctx,
        customer=customer,
        member=member,
        lines=lines,
        start=start,
        minutes=minutes,
        source=data.source,
        notes=data.notes,
        internal_notes=data.internal_notes,
        settings=current_settings(),
    )
    return load_detail(ctx, appointment.id)


@operation(
    "appointment.appointment.bulk_create",
    kind="command",
    permission=ADD_OWN,
    input=BulkCreateIn,
    output=AppointmentsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "book Carmen's five sessions every Monday at 4 pm in one go",
                "make three appointments for Julia at once, all or none",
            ),
            "es": (
                "dale de golpe a Carmen sus cinco sesiones, los lunes a las 16:00",
                "mete tres citas a Julia a la vez, todas o ninguna",
            ),
        },
        "description": "Book several times at once (1 to 50) for the same customer, services and professional (a "
        "voucher's sessions, a course). All or none: the first time that does not fit refuses the whole batch with "
        "its reason.",
        "risk": "normal",
    },
)
def bulk_create(ctx: OperationContext, data: BulkCreateIn) -> dict:
    customer, member, lines, minutes = _booking_basis(ctx, data)
    starts = sorted(read_moment(value, "starts") for value in data.starts)
    zone = business_zone()
    agenda = load_agenda(
        ctx,
        member,
        engine.wall(starts[0], zone).date(),
        engine.wall(engine.ends_at(starts[-1], minutes), zone).date(),
    )
    settings = current_settings()
    created = []
    for start in starts:
        end = engine.ends_at(start, minutes)
        try:
            _judge(
                ctx,
                member,
                start,
                end,
                customer=False,
                confirm_overlap=data.confirm_overlap,
                agenda=agenda,
            )
        except Conflict as refusal:
            raise Conflict(
                str(BATCH_AT) % {"time": _short(start), "reason": refusal.message},
                code=refusal.code,
            ) from None
        appointment = _create(
            ctx,
            customer=customer,
            member=member,
            lines=lines,
            start=start,
            minutes=minutes,
            source=Appointment.Source.COUNTER,
            notes=data.notes,
            settings=settings,
        )
        agenda = replace(
            agenda,
            busy=[*agenda.busy, engine.Period(start, end, id=appointment.id, label=appointment.number)],
        )
        created.append(appointment.id)
    return {"rows": [load_detail(ctx, appointment_id) for appointment_id in created]}
