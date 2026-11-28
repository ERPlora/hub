"""A ticket by hand (KITCHEN-F23)."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.kitchen import events
from apps.kitchen.models.fields import ACTOR_MAX_LENGTH, Destination
from apps.kitchen.models.history import LogAction
from apps.kitchen.models.tickets import Ticket, TicketItem
from apps.kitchen.queries.reads import business_day
from apps.kitchen.queries.routing import routing
from apps.kitchen.schemas.tickets import TicketCreateIn, TicketOut
from apps.kitchen.services.catalog import find_product
from apps.kitchen.services.paper import _print_round
from apps.kitchen.services.settling import begin, out
from apps.kitchen.services.writes import _ticket_event, actor, take_number, write_log
from base.assistant import card_order
from base.queries.people import actor_name


@operation(
    "kitchen.ticket.create",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketCreateIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "put through a crew meal with two burgers",
                "add a dish to remake by hand",
            ),
            "es": (
                "haz una comanda a mano para rehacer una ensalada",
                "crea una comanda con dos bocadillos para el almuerzo",
            ),
        },
        "description": "Make a kitchen ticket by hand, with no check (a staff meal, a dish to remake): its type, "
        "where it goes, notes and its dishes (products of the catalogue by name, or free text), each to its station.",
        "risk": "normal",
        "summary": card_order.said_first("label", "items"),
    },
)
def create_ticket(ctx: OperationContext, data: TicketCreateIn) -> dict:
    settings = begin(ctx)
    now = timezone.now()
    day = business_day(now)
    sequence = take_number(day)
    ticket = Ticket.objects.create(
        number=f"{day:%Y%m%d}-{sequence:04d}",
        day=day,
        sequence=sequence,
        label=data.label,
        order_type=data.order_type or settings.default_order_type,
        notes=data.notes,
        waiter=actor_name(ctx.actor)[:ACTOR_MAX_LENGTH],
        received_at=now,
        created_by=actor(ctx),
    )
    route = routing()
    items = []
    for position, dish in enumerate(data.items, start=1):
        product = (
            find_product(dish.product_id, dish.product)
            if dish.product_id or dish.product
            else None
        )
        category_id = (
            product.categories.order_by("name", "id")
            .values_list("id", flat=True)
            .first()
            if product
            else None
        )
        station = route.station_for(product.id, category_id) if product else None
        total = (
            (Decimal(product.price) * dish.quantity).quantize(
                Decimal("1"), ROUND_HALF_UP
            )
            if product
            else 0
        )
        items.append(
            TicketItem(
                ticket=ticket,
                position=position,
                product_id=product.id if product else None,
                category_id=category_id,
                name=product.name if product else dish.name,
                quantity=dish.quantity,
                unit=product.unit if product else "ud",
                notes=dish.notes,
                station=station,
                station_name=station.name if station else "",
                destination=station.destination if station else Destination.BOTH,
                printer_usage=station.printer_usage if station else "kitchen",
                printer_name=station.printer_name if station else "",
                total=int(total),
            )
        )
    TicketItem.objects.bulk_create(items)
    ticket.total = sum(item.total for item in items)
    ticket.save(update_fields=["total"])
    write_log(ticket.id, LogAction.CREATED, who=actor(ctx), at=now)
    _ticket_event(ctx, events.TICKET_CREATED, ticket)
    return out(ticket, _print_round(ctx, ticket))
