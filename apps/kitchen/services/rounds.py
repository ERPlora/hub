"""Receiving and sending rounds (KITCHEN-F05, F18): the till sends a check's pending lines, the reaction
receives a round Sales fired, and the system brings the kitchen up to date.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import get, operation

from apps.kitchen import events
from apps.kitchen.models import ACTOR_MAX_LENGTH, Ticket, TicketItem
from apps.kitchen.queries.reads import COOKING
from apps.kitchen.schemas import ReceivedOut, SyncOut, TicketOut, TicketReceiveIn, TicketSendIn, TicketSyncIn
from apps.kitchen.services.paper import _print_round
from apps.kitchen.services.settling import begin, out, settle
from apps.kitchen.services.writes import _ticket_event, locked_row, locked_settings
from apps.sale.models import OrderLine
from base.queries.people import actor_name

NOTHING_TO_COOK = _("Nothing on this check is cooked: services do not go to the kitchen.")


def _round_ticket(line_ids) -> Ticket | None:
    """The ticket of the round of ``line_ids``, locked until the end of the write; none if it was never saved
    or was deleted since."""
    ticket_id = (
        TicketItem.objects.filter(sale_line_id__in=list(line_ids))
        .values_list("ticket_id", flat=True)
        .first()
    )
    return locked_row(Ticket, ticket_id) if ticket_id is not None else None


def _enrich(  # noqa: PLR0913
    ctx: OperationContext,
    ticket: Ticket,
    *,
    label: str,
    channel: str,
    priority: str,
    waiter: str,
) -> Ticket:
    """What only the send knows (its label, channel, priority and who sent it), on the round's ticket (locked
    by ``_round_ticket``)."""
    before = (ticket.label, ticket.order_type, ticket.priority, ticket.waiter)
    ticket.label = (label or ticket.label)[:120]
    ticket.order_type = channel
    ticket.waiter = (waiter or ticket.waiter)[:ACTOR_MAX_LENGTH]
    if (
        priority != "normal"
        and ticket.status in COOKING
        and ticket.priority == "normal"
    ):
        ticket.priority = priority
    if (ticket.label, ticket.order_type, ticket.priority, ticket.waiter) != before:
        ticket.save(
            update_fields=["label", "order_type", "priority", "waiter", "updated_at"]
        )
        _ticket_event(ctx, events.TICKET_UPDATED, ticket, priority=ticket.priority)
    return ticket


@operation(
    "kitchen.ticket.send",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketSendIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "send what is left on table 4, urgent",
                "fire another round of this check",
            ),
            "es": (
                "manda lo que falta de la mesa 4, urgente",
                "envía otra ronda de esta cuenta",
            ),
        },
        "description": "Send to the kitchen what is pending on an open check, as a new round, normal or rush "
        "(«send table 4 to the kitchen, urgent»): Sales marks the lines sent and the kitchen opens the ticket and "
        "prints it on its stations' printers.",
        "risk": "normal",
    },
)
def send(ctx: OperationContext, data: TicketSendIn) -> dict:
    fire = get("sale.order.fire")
    fired = fire(
        ctx,
        fire.input.model_validate(
            {
                "order_id": str(data.order_id),
                "label": data.label,
                "channel": data.channel,
                "priority": "urgent" if data.priority == "rush" else "",
                "waiter": data.waiter,
            }
        ),
    )
    begin(ctx)
    lines = OrderLine.objects.filter(
        order_id=data.order_id, round_no=fired.round_no, fired_at__isnull=False
    )
    newest = lines.order_by("-fired_at").values_list("fired_at", flat=True).first()
    ticket = _round_ticket(lines.filter(fired_at=newest).values_list("id", flat=True))
    if ticket is None:
        # Only services: nothing to cook; the refusal rolls the send back, so Sales marks nothing sent.
        raise Conflict(str(NOTHING_TO_COOK), code="kitchen.nothing_to_cook")
    ticket = _enrich(
        ctx,
        ticket,
        label=data.label or fired.order.label,
        channel=data.channel,
        priority=data.priority,
        # Whoever the till names, else who serves the check (kept on it), else who sends it.
        waiter=data.waiter or fired.order.staff_name or actor_name(ctx.actor),
    )
    return out(ticket, _print_round(ctx, ticket))


@operation(
    "kitchen.ticket.receive",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketReceiveIn,
    output=ReceivedOut,
    ai={
        "asks": {
            "en": (
                "take in the round table 4 just fired",
                "open the last round sent from table 2",
            ),
            "es": (
                "la mesa 4 acaba de mandar otra ronda: recíbela",
                "recibe la ronda de la mesa 2",
            ),
        },
        "description": "Open the kitchen ticket of a round Sales already fired (the reaction to a round sent), with "
        "its priority, channel and who sent it, and print it. Receiving it twice opens it once.",
        "risk": "normal",
    },
)
def receive(ctx: OperationContext, data: TicketReceiveIn) -> dict:
    begin(ctx)
    line_ids = [item.order_item_id for item in data.items]
    if not line_ids:
        lines = OrderLine.objects.filter(
            order_id=data.order_id, round_no=data.round_no, fired_at__isnull=False
        )
        line_ids = list(lines.values_list("id", flat=True))
    ticket = _round_ticket(line_ids)
    if ticket is None:
        return {"ticket": None}
    ticket = _enrich(
        ctx,
        ticket,
        label=data.label,
        channel=data.channel,
        priority=data.priority,
        waiter=data.waiter,
    )
    return {"ticket": out(ticket, _print_round(ctx, ticket))}


@operation(
    "kitchen.ticket.sync",
    kind="command",
    permission="kitchen.system",
    input=TicketSyncIn,
    output=SyncOut,
    ai={
        "description": "Bring the kitchen up to date with what Sales did (rounds fired, checks charged or voided, "
        "lines voided): the system's reaction.",
        "risk": "normal",
    },
)
def sync(ctx: OperationContext, data: TicketSyncIn) -> dict:
    received, changed = settle(ctx, locked_settings())
    return {"received": received, "changed": changed}
