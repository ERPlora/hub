"""The appointments: the agenda's list, one of them, its history, a customer's, and the counters."""

from django.db.models import Exists, OuterRef
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.appointment.models import Appointment, AppointmentService, History
from apps.appointment.schemas.agenda import AppointmentListIn, AppointmentPage
from apps.appointment.schemas.appointments import (
    AppointmentOut,
    AppointmentRefIn,
    CountForServiceIn,
    CountOut,
    ForCustomerIn,
    HistoryIn,
    HistoryPage,
    VisitPage,
)
from apps.appointment.schemas.fields import NoIn, PageIn
from apps.customer.queries.reads import find_customer
from apps.service.queries import catalog
from apps.staff.queries.reads import resolve_member
from base.business import business_zone, zone_name
from base.ordering import list_order_for
from base.relay import by_platform
from base.text_search import contains_text

from .access import VIEW_OWN, for_caller
from .business import day_bounds, now
from .reads import MOVABLE, S, _page, appointments, detail, find_appointment, row

APPOINTMENT_ORDER = {
    "start": ("start",),
    "number": ("number",),
    "customer_name": ("customer_name",),
    "staff_name": ("staff_name",),
    "status": ("status",),
}


@operation(
    "appointment.appointment.list",
    kind="query",
    permission=VIEW_OWN,
    input=AppointmentListIn,
    output=AppointmentPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what appointments do we have on Friday?",
                "show me next week's appointments with Lucía",
            ),
            "es": (
                "¿qué citas hay el viernes?",
                "enséñame las citas de la semana que viene con Lucía",
            ),
        },
        "description": "List the appointments of one business day or a range of days (on the business's clock), "
        "with customer, services, professional, status and whether they are charged; filter by professional (name), "
        "status, customer or a search text. Contact details and notes are not included."
    },
)
def list_appointments(ctx: OperationContext, params: AppointmentListIn) -> dict:
    start, end = day_bounds(params.date_from, params.date_to)
    rows = appointments(ctx).filter(start__gte=start, start__lt=end)
    if params.staff_id or params.staff:
        rows = rows.filter(staff=resolve_member(params.staff_id, params.staff))
    if params.unassigned is not None:
        rows = rows.filter(staff__isnull=params.unassigned)
    if params.customer_id:
        rows = rows.filter(customer_id=params.customer_id)
    if params.status:
        rows = rows.filter(status=params.status)
    if params.search:
        text = params.search
        named = AppointmentService.objects.filter(contains_text(text, "name"), appointment=OuterRef("pk"))
        rows = rows.filter(contains_text(text, "number", "customer_name") | Exists(named))
    page = _page(
        rows.order_by(*list_order_for(params.sort, columns=APPOINTMENT_ORDER)),
        params.limit,
        params.offset,
        row,
    )
    return {**page, "timezone": zone_name()}


@operation(
    "appointment.appointment.get",
    kind="query",
    permission=VIEW_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me appointment APT-0042",
                "what phone number is on appointment 17?",
            ),
            "es": (
                "enséñame la cita APT-0042",
                "¿qué teléfono tiene puesto la cita número 17?",
            ),
        },
        "description": "Get one appointment by its id or its number (APT-…), with contact, notes and charge."
    },
)
def get_appointment(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return detail(ctx, find_appointment(ctx, data.id, data.number))


@operation(
    "appointment.appointment.history",
    kind="query",
    permission=VIEW_OWN,
    input=HistoryIn,
    output=HistoryPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who moved Pilar's appointment and when?",
                "show me the history of appointment APT-0042",
            ),
            "es": (
                "¿quién movió la cita de Pilar y cuándo?",
                "historial de cambios de la cita APT-0042",
            ),
        },
        "description": "The history of one appointment: every change, when, who did it (or that the customer asked), "
        "and what changed (time, professional, service, status, charge)."
    },
)
def appointment_history(ctx: OperationContext, data: HistoryIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number)
    rows = History.objects.filter(appointment=appointment).order_by("at", "id")

    def out(line: History) -> dict:
        return {
            "id": line.id,
            "action": line.action,
            "at": line.at.astimezone(business_zone()),
            "actor": line.actor,
            "by_customer": line.by_customer,
            "by_platform": by_platform(line.actor),
            "reason": line.reason,
            "old_value": line.old_value,
            "new_value": line.new_value,
        }

    return _page(rows, data.limit, data.offset, out)


@operation(
    "appointment.appointment.list_for_customer",
    kind="query",
    permission=VIEW_OWN,
    input=ForCustomerIn,
    output=VisitPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which appointments has Teresa had with us?",
                "Teresa's past and upcoming appointments",
            ),
            "es": (
                "¿qué citas ha tenido Teresa con nosotros?",
                "todas las citas de Teresa, pasadas y futuras",
            ),
        },
        "description": "A customer's appointments, the newest first (named by her name, phone or email), with "
        "services, professional, status and the visit's notes (the internal one may hold a colour formula)."
    },
)
def list_for_customer(ctx: OperationContext, params: ForCustomerIn) -> dict:
    customer = find_customer(
        ctx,
        params.customer_id, params.customer, live=params.customer_id is None
    )
    rows = (
        appointments(ctx).filter(customer=customer).order_by("-start", "-id")
    )
    return _page(
        rows,
        params.limit,
        params.offset,
        lambda item: for_caller(
            ctx,
            {**row(item), "notes": item.notes, "internal_notes": item.internal_notes},
        ),
    )


@operation(
    "appointment.appointment.count_active_for_service",
    kind="query",
    permission=VIEW_OWN,
    input=CountForServiceIn,
    output=CountOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many upcoming appointments still include the keratin treatment?",
                "are there future appointments with highlights before I archive them?",
            ),
            "es": (
                "¿cuántas citas futuras llevan todavía el alisado de keratina?",
                "antes de archivar las mechas, ¿cuántas citas por delante las incluyen?",
            ),
        },
        "description": "How many upcoming live appointments (pending or confirmed) carry a service, and when the "
        "first one is: what to warn about before archiving the service."
    },
)
def count_active_for_service(ctx: OperationContext, data: CountForServiceIn) -> dict:
    service = catalog.find_service(data.service_id, data.service)
    rows = Appointment.objects.filter(
        deleted_at__isnull=True, status__in=MOVABLE, start__gte=now(), lines__service=service
    ).distinct()
    first = rows.order_by("start", "id").first()
    return {
        "count": rows.count(),
        "earliest": first.start.astimezone(business_zone()) if first else None,
    }


@operation(
    "appointment.appointment.count_to_confirm",
    kind="query",
    permission=VIEW_OWN,
    input=NoIn,
    output=CountOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many appointments still need my confirmation?",
                "are any appointments left unconfirmed?",
            ),
            "es": (
                "¿cuántas citas me quedan por confirmar?",
                "¿hay citas sin confirmar todavía?",
            ),
        },
        "description": "How many upcoming appointments are still pending: bookings to confirm."
    },
)
def count_to_confirm(ctx: OperationContext, data: NoIn) -> dict:
    rows = _to_confirm(ctx)
    first = rows.first()
    return {
        "count": rows.count(),
        "earliest": first.start.astimezone(business_zone()) if first else None,
    }


@operation(
    "appointment.appointment.list_to_confirm",
    kind="query",
    permission=VIEW_OWN,
    input=PageIn,
    output=AppointmentPage,
    ai=INTERNAL,
)
def list_to_confirm(ctx: OperationContext, params: PageIn) -> dict:
    page = _page(_to_confirm(ctx), params.limit, params.offset, row)
    return {**page, "timezone": zone_name()}


def _to_confirm(ctx: OperationContext):
    """The bookings still waiting for confirmation, of any day, soonest first: what «N to confirm» counts and lists."""
    return appointments(ctx).filter(status=S.PENDING, start__gte=now()).order_by("start", "id")
