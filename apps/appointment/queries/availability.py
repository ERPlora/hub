"""The free times of a day, and whether a time can be booked and why not."""

import datetime as dt

from live.context import OperationContext
from live.operations import operation

from apps.appointment import engine
from apps.appointment.schemas.availability import CheckIn, CheckOut, SlotsIn, SlotsOut
from apps.service.models.catalog import Service
from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member
from base.business import business_zone, zone_name

from .agenda import conflicts_of, load_agenda, verdict_message
from .booking import MAX_PROFESSIONALS, bookable_members, lines_for, resolve_services
from .business import current_settings, now, read_moment
from .ownership import sees_whose


def _who_and_how_long(
    services_refs, staff_id, staff, minutes
) -> tuple[list[Service], list[Member], dict]:
    """The services, the professionals to look at and each one's length (``minutes`` wins)."""
    services = resolve_services(services_refs) if services_refs else []
    if staff_id or staff:
        members = [resolve_member(staff_id, staff)]
    elif services:
        members = bookable_members(services)
    else:
        members = list(
            Member.objects.filter(
                status=Member.Status.ACTIVE, is_bookable=True
            ).order_by("first_name", "last_name", "id")[:MAX_PROFESSIONALS]
        )
    lengths = {
        member.id: minutes
        or sum(line["duration_minutes"] for line in lines_for(member, services))
        for member in members
    }
    return services, members, lengths


@operation(
    "appointment.availability.slots",
    kind="query",
    permission="appointment.view_schedule",
    input=SlotsIn,
    output=SlotsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what free times are there on Saturday for a manicure?",
                "when could Inés fit a colour on Thursday?",
            ),
            "es": (
                "¿qué horas libres hay el sábado para una manicura?",
                "¿a qué horas puede coger Inés un tinte el jueves?",
            ),
        },
        "description": "The free times of a business day to book some services (or a length), for one professional "
        "(by name) or for anybody who does them: each time says which professionals are free. It crosses the "
        "opening hours (Schedules), each professional's shift and time off (Staff), blocked time and the appointments "
        "already booked. for_customer=true when the customer books herself (the minimum notice applies)."
    },
)
def availability_slots(ctx: OperationContext, data: SlotsIn) -> dict:
    services, members, lengths = _who_and_how_long(
        data.service_refs(), data.staff_id, data.staff, data.duration_minutes
    )
    settings = current_settings()
    moment = now()
    found: dict[dt.datetime, dict] = {}
    for member in members:
        agenda = load_agenda(
            ctx,
            member,
            data.date,
            data.date,
            exclude=(data.exclude_id,),
            settings=settings,
        )
        for slot in engine.slots(
            agenda,
            data.date,
            lengths[member.id],
            now=moment,
            customer=data.for_customer,
        ):
            entry = found.setdefault(
                slot.start,
                {
                    "start": slot.start,
                    "end": slot.end,
                    "within_notice": slot.within_notice,
                    "staff_ids": [],
                },
            )
            entry["staff_ids"].append(member.id)
    if not members:
        agenda = load_agenda(ctx, None, data.date, data.date, settings=settings)
        minutes = (
            data.duration_minutes
            or sum(s.duration_minutes for s in services)
            or settings.default_duration
        )
        for slot in engine.slots(
            agenda, data.date, minutes, now=moment, customer=data.for_customer
        ):
            found[slot.start] = {
                "start": slot.start,
                "end": slot.end,
                "within_notice": slot.within_notice,
                "staff_ids": [],
            }
    zone = business_zone()
    duration = (
        lengths[members[0].id]
        if len(members) == 1
        else data.duration_minutes
        or sum(s.duration_minutes for s in services)
        or settings.default_duration
    )
    return {
        "date": data.date,
        "timezone": zone_name(),
        "duration_minutes": duration,
        "slots": [
            {
                **entry,
                "start": entry["start"].astimezone(zone),
                "end": entry["end"].astimezone(zone),
            }
            for _, entry in sorted(found.items())
        ],
    }


@operation(
    "appointment.availability.check",
    kind="query",
    permission="appointment.view_schedule",
    input=CheckIn,
    output=CheckOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "check if Sara can take an appointment on Friday at 6 pm",
                "is 9:30 tomorrow bookable, and if not, why?",
            ),
            "es": (
                "¿se puede dar cita a Sara el viernes a las 18:00?",
                "¿mañana a las 9:30 se puede citar a alguien o por qué no?",
            ),
        },
        "description": "Whether a time can be booked (for a professional, by name, or the business alone) and why not: "
        "invalid_start, in_past, too_soon, too_far, outside_schedule (the business is shut), outside_staff_hours (the "
        "professional does not work then or is off), blocked or overlap (with the appointments it overlaps). The same "
        "rules a booking applies."
    },
)
def availability_check(ctx: OperationContext, data: CheckIn) -> dict:
    start = read_moment(data.start, "start")
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else None
    )
    refs = data.service_refs()
    services = resolve_services(refs) if refs else []
    minutes = data.duration_minutes or sum(
        line["duration_minutes"] for line in lines_for(member, services)
    )
    end = engine.ends_at(start, minutes)
    zone = business_zone()
    agenda = load_agenda(
        ctx,
        member,
        engine.wall(start, zone).date(),
        engine.wall(end, zone).date(),
        exclude=(data.exclude_id,),
    )
    code = engine.verdict(agenda, start, end, now=now(), customer=data.for_customer)
    return {
        "available": code is None,
        "code": code,
        "message": verdict_message(code) if code else "",
        # Whose appointments they are only for who may see that agenda: a colleague's time is just taken.
        "conflicts": conflicts_of(agenda, start, end) if member and sees_whose(ctx, member.id) else [],
    }
