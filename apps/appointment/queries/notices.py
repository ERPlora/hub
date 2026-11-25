"""What the team is told as it happens (APPOINTMENT-F28): the customers' own bookings and cancellations."""

import datetime as dt

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.appointment.schemas.appointments import NoticesIn, NoticesOut
from base.business import business_zone

from .access import VIEW_OWN
from .reads import CUSTOMER_SOURCES, appointments, row, start_labels

#: How far back the notices go when nobody says.
NOTICES_WINDOW = dt.timedelta(hours=24)


@operation(
    "appointment.appointment.notices",
    kind="query",
    permission=VIEW_OWN,
    input=NoticesIn,
    output=NoticesOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which appointments did customers book themselves this week?",
                "any appointments the customers cancelled on their own lately?",
            ),
            "es": (
                "¿qué citas han cogido las clientas ellas mismas esta semana?",
                "¿qué citas han anulado los propios clientes últimamente?",
            ),
        },
        "description": "What customers did themselves lately (WhatsApp, the online booking): the appointments they "
        "booked and the ones they cancelled, the newest first, with who, which services, when and with whom."
    },
)
def notices(ctx: OperationContext, data: NoticesIn) -> dict:
    """The customer's own bookings and cancellations since ``data.since`` (the front desk's are not told: who
    gave or cancelled it knows), of the agenda the caller sees, the newest first."""
    since = data.since or timezone.now() - NOTICES_WINDOW
    rows = appointments(ctx)
    told = [
        ("booked", item.created_at, item)
        for item in rows.filter(source__in=CUSTOMER_SOURCES, created_at__gte=since)
    ] + [
        ("cancelled", item.cancelled_at, item)
        for item in rows.filter(cancelled_by_customer=True, cancelled_at__gte=since)
    ]
    told.sort(key=lambda notice: (notice[1], notice[2].id, notice[0] == "cancelled"), reverse=True)
    return {
        "rows": [
            {
                "kind": kind,
                "at": at,
                "id": item.id,
                "number": item.number,
                "customer_name": item.customer_name,
                "service_names": row(item)["service_names"],
                "staff_name": item.staff_name,
                "start": item.start.astimezone(business_zone()),
                **start_labels(ctx, item.start),
            }
            for kind, at, item in told[: data.limit]
        ]
    }
