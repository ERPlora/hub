"""Settling: the rounds Sales fired and what it did after, saved at the start of every write on tickets; and
the ticket a write locks, its output and the steps it may take.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.outbox import record_event

from apps.kitchen import events
from apps.kitchen.models import (
    ACTOR_MAX_LENGTH,
    ItemStatus,
    KitchenSettings,
    LogAction,
    Ticket,
    TicketItem,
    TicketStatus,
)
from apps.kitchen.queries.outputs import ticket_out
from apps.kitchen.queries.reads import COOKING, IN_FLIGHT, STRUCK, business_day
from apps.kitchen.queries.rounds import pending_rounds, round_view
from apps.kitchen.queries.routing import routing
from apps.kitchen.queries.scope import station_map
from apps.kitchen.queries.state import effective
from apps.kitchen.queries.tickets import TICKET_NOT_FOUND, find_ticket_view
from apps.kitchen.queries.views import Change, TicketView, saved_views
from apps.kitchen.schemas.fields import TicketRefIn
from apps.kitchen.services.paper import CANCELLED_TICKET, VOIDED_DISH, _pass, _void_slip
from apps.kitchen.services.writes import (
    _ticket_event,
    actor,
    locked_row,
    locked_settings,
    logger,
    take_number,
    write_log,
)

INVALID_TRANSITION = _(
    "That kitchen ticket is no longer in the state this action requires. Refresh and try again."
)

#: The steps of a ticket: action → the statuses it may start from.
ALLOWED = {
    "start": (TicketStatus.PENDING,),
    "ready": COOKING,
    "serve": (TicketStatus.READY,),
    "recall": (TicketStatus.READY,),
    "cancel": IN_FLIGHT,
}


def save_round(ctx: OperationContext, rnd, route) -> Ticket:
    """Save a round of Sales as the board showed it: its first line's id, the next number of its day."""
    day = business_day(rnd.fired_at)
    view = round_view(rnd, day, take_number(day), route)
    ticket = Ticket.objects.create(
        id=view.id,
        number=view.number,
        day=view.day,
        sequence=view.sequence,
        order_id=view.order_id,
        round_no=view.round_no,
        label=view.label,
        waiter=view.waiter[:ACTOR_MAX_LENGTH],
        received_at=view.received_at,
        total=view.total,
        created_by=actor(ctx),
    )
    TicketItem.objects.bulk_create(
        [
            TicketItem(
                id=item.id,
                ticket=ticket,
                sale_line_id=item.sale_line_id,
                menu_dish=item.menu_dish,
                menu_name=item.menu_name[:200],
                position=item.position,
                product_id=item.product_id,
                category_id=item.category_id,
                name=item.name[:200],
                quantity=item.quantity,
                unit=item.unit,
                notes=item.notes[:255],
                modifiers=item.modifiers,
                allergy=item.allergy,
                allergy_in_dish=item.allergy_in_dish,
                station_id=item.station_id,
                station_name=item.station_name,
                destination=item.destination,
                printer_usage=item.printer_usage,
                printer_name=item.printer_name,
                total=item.total,
            )
            for item in view.items
        ]
    )
    write_log(ticket.id, LogAction.RECEIVED, at=view.received_at)
    _ticket_event(ctx, events.TICKET_RECEIVED, ticket, order_id=str(ticket.order_id), round_no=ticket.round_no)
    return ticket


def _persist(
    ctx: OperationContext,
    before: TicketView,
    after: TicketView,
    changes: list[Change],
    settings: KitchenSettings,
) -> bool:
    """Save what Sales did to a ticket (``effective``): its states, its History and events, its slips. One
    deleted since it was read is left as it is (``False``)."""
    ticket = locked_row(Ticket, after.id)
    if ticket is None:
        return False
    ticket.status = after.status
    ticket.started_at = after.started_at
    ticket.ready_at = after.ready_at
    ticket.served_at = after.served_at
    ticket.cancelled_at = after.cancelled_at
    ticket.total = after.total
    ticket.save(
        update_fields=[
            "status",
            "started_at",
            "ready_at",
            "served_at",
            "cancelled_at",
            "total",
            "updated_at",
        ]
    )
    old = {item.id: item for item in before.items}
    for item in after.items:
        was = old[item.id]
        if (item.status, item.void_reason, item.ready_at) != (
            was.status,
            was.void_reason,
            was.ready_at,
        ):
            TicketItem.objects.filter(pk=item.id).update(
                status=item.status,
                void_reason=item.void_reason[:255],
                ready_at=item.ready_at,
            )
    items = {item.id: item for item in after.items}
    for change in changes:
        if change.kind == "item_voided":
            item = items[change.item_id]
            write_log(
                ticket.id,
                LogAction.ITEM_VOIDED,
                notes=change.notes,
                at=change.at,
                item_id=item.id,
                station_id=item.station_id,
            )
            record_event(
                ctx,
                events.ITEM_VOIDED,
                {
                    "ticket_id": str(ticket.id),
                    "item_ids": [str(item.id)],
                    "reason": change.notes,
                },
            )
            _void_slip(
                ctx, ticket, [old[item.id]], key=f"void-{item.id}", title=VOIDED_DISH
            )
        elif change.kind == "cancelled":
            write_log(ticket.id, LogAction.CANCELLED, at=change.at)
            _ticket_event(ctx, events.TICKET_CANCELLED, ticket, reason="")
            # The dishes voided one by one already had their own slip.
            alive = [
                old[item.id]
                for item in after.items
                if old[item.id].status not in (*STRUCK, ItemStatus.SERVED)
            ]
            alive = [
                item for item in alive if items[item.id].status != ItemStatus.VOIDED
            ]
            _void_slip(ctx, ticket, alive, key="cancel", title=CANCELLED_TICKET)
        elif change.kind == "ready":
            write_log(ticket.id, LogAction.READY, at=change.at)
            _ticket_event(ctx, events.TICKET_READY, ticket)
            # The pass, as when a cook marks it ready (KITCHEN-F17: every time it turns ready).
            outcome = _pass(ctx, ticket, settings)
            if outcome:
                logger.warning("kitchen: the pass of %s was not printed: %s", ticket.number, outcome)
        elif change.kind == "served":
            write_log(ticket.id, LogAction.SERVED, at=change.at)
            _ticket_event(ctx, events.TICKET_SERVED, ticket)
    return True


def _retitle(ctx: OperationContext, ticket: Ticket, label: str) -> None:
    """The title of its check now, saved: the History and the search of a served ticket say where it went."""
    ticket.label = label[:120]
    ticket.save(update_fields=["label", "updated_at"])
    _ticket_event(ctx, events.TICKET_UPDATED, ticket)


def settle(ctx: OperationContext, settings: KitchenSettings) -> tuple[int, int]:
    """Save the rounds not saved yet (in the order of their numbers) and what Sales did to the tickets on
    the line. Returns ``(rounds saved, tickets changed)``."""
    rounds = pending_rounds(settings)
    if rounds:
        route = routing()
        for rnd in rounds:
            save_round(ctx, rnd, route)
    changed = 0
    on_the_line = list(
        Ticket.objects.filter(is_deleted=False, status__in=IN_FLIGHT).prefetch_related("items")
    )
    for ticket, view in zip(on_the_line, saved_views(on_the_line), strict=True):
        if view.label != ticket.label:
            _retitle(ctx, ticket, view.label)
        after, changes = effective(view, settings)
        if changes and _persist(ctx, view, after, changes, settings):
            changed += 1
    return len(rounds), changed


def begin(ctx: OperationContext) -> KitchenSettings:
    """The start of every write on tickets: the lock, then everything saved."""
    settings = locked_settings()
    settle(ctx, settings)
    return settings


def locked_ticket(ref: TicketRefIn, settings: KitchenSettings) -> Ticket:
    """The ticket ``ref`` names, locked until the end of the write (not found if deleted since it was found)."""
    ticket = locked_row(Ticket, find_ticket_view(ref, settings).id)
    if ticket is None:
        raise NotFound(str(TICKET_NOT_FOUND), code="kitchen.ticket_not_found")
    return ticket


def out(ticket: Ticket, print_error: str | None = None) -> dict:
    ticket = Ticket.objects.prefetch_related("items").get(pk=ticket.pk)
    return ticket_out(saved_views([ticket])[0], station_map(), print_error)


def require(ticket: Ticket, action: str) -> None:
    if ticket.status not in ALLOWED[action]:
        raise Conflict(str(INVALID_TRANSITION), code="kitchen.invalid_transition")
