"""The journey of a ticket (KITCHEN-F13, F17, F21): start, ready, serve, recall, cancel, delete, rush and
reprint.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.kitchen import events
from apps.kitchen.models.history import LogAction
from apps.kitchen.models.tickets import ItemStatus, Ticket, TicketStatus
from apps.kitchen.queries.reads import COOKING, STRUCK, TO_DO
from apps.kitchen.schemas.fields import DeletedOut, TicketRefIn
from apps.kitchen.schemas.tickets import TicketCancelIn, TicketOut, TicketRushIn
from apps.kitchen.services.paper import (
    CANCELLED_TICKET,
    UNAVAILABLE,
    _dishes,
    _error,
    _paper,
    _pass,
    _went_to_paper,
    print_ticket,
)
from apps.kitchen.services.settling import begin, locked_ticket, out, require
from apps.kitchen.services.writes import _ticket_event, actor, write_log

NOT_COOKING = _("That ticket is no longer being cooked.")
VIP_TICKET = _("That ticket is VIP: a rush does not change its priority.")
NOT_DELETABLE = _(
    "That ticket cannot be deleted: it comes from a check or it is already being cooked. Cancel it instead."
)
NOTHING_ON_PAPER = _(
    "Nothing of this ticket goes to paper: its stations are screen only."
)
PRINTING_UNAVAILABLE = _("No printer prints this ticket: turn on Printing and add an active kitchen or bar printer.")
PRINT_FAILED = _("The ticket could not be printed: %(reason)s")


@operation(
    "kitchen.ticket.start",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "start cooking number 12",
                "begin cooking number 7 now",
            ),
            "es": (
                "empieza con la comanda 12",
                "inicia ya la comanda 7",
            ),
        },
        "description": "Start cooking a ticket («fire table 4»): it and its dishes go to preparing.",
        "risk": "normal",
    },
)
def start_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    require(ticket, "start")
    now = timezone.now()
    ticket.status, ticket.started_at = TicketStatus.PREPARING, now
    ticket.save(update_fields=["status", "started_at", "updated_at"])
    ticket.items.filter(status=ItemStatus.PENDING).update(status=ItemStatus.PREPARING)
    write_log(ticket.id, LogAction.STARTED, who=actor(ctx), at=now)
    _ticket_event(ctx, events.TICKET_STARTED, ticket)
    return out(ticket)


@operation(
    "kitchen.ticket.ready",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "everything on number 12 is ready for the pass",
                "number 7 is ready to go, all of it",
            ),
            "es": (
                "la comanda 12 ya está acabada entera",
                "la 7 ya está hecha, que vaya al pase",
            ),
        },
        "description": "Mark a whole ticket ready, every dish of it («table 4 is ready»): it goes to the pass.",
        "risk": "normal",
    },
)
def ready_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    require(ticket, "ready")
    now = timezone.now()
    ticket.items.filter(status__in=TO_DO).update(status=ItemStatus.READY, ready_at=now)
    ticket.status, ticket.ready_at = TicketStatus.READY, now
    ticket.started_at = ticket.started_at or now
    ticket.save(update_fields=["status", "ready_at", "started_at", "updated_at"])
    write_log(ticket.id, LogAction.READY, who=actor(ctx), at=now)
    _ticket_event(ctx, events.TICKET_READY, ticket)
    return out(ticket, _pass(ctx, ticket, settings))


@operation(
    "kitchen.ticket.serve",
    kind="command",
    permission="kitchen.complete_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "number 12 has gone out",
                "number 7 is out of the pass",
            ),
            "es": (
                "la 12 ya ha salido del pase",
                "da por servida la comanda 7",
            ),
        },
        "description": "Mark a ready ticket served («table 4 is out»): it leaves the pass.",
        "risk": "normal",
    },
)
def serve_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    require(ticket, "serve")
    now = timezone.now()
    ticket.items.filter(status=ItemStatus.READY).update(status=ItemStatus.SERVED)
    ticket.status, ticket.served_at = TicketStatus.SERVED, now
    ticket.save(update_fields=["status", "served_at", "updated_at"])
    write_log(ticket.id, LogAction.SERVED, who=actor(ctx), at=now)
    _ticket_event(ctx, events.TICKET_SERVED, ticket)
    return out(ticket)


@operation(
    "kitchen.ticket.recall",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "bring number 12 back from the pass, it is not finished",
                "we marked number 7 ready by mistake, recall it",
            ),
            "es": (
                "recupera la 12 del pase, que no estaba acabada",
                "la comanda 7 vuelve a preparación, falta algo",
            ),
        },
        "description": "Recall a ticket marked ready by mistake: it goes back to preparing with its ready dishes.",
        "risk": "normal",
    },
)
def recall_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    require(ticket, "recall")
    ticket.items.filter(status=ItemStatus.READY).update(
        status=ItemStatus.PREPARING, ready_at=None
    )
    ticket.status, ticket.ready_at = TicketStatus.PREPARING, None
    ticket.save(update_fields=["status", "ready_at", "updated_at"])
    write_log(ticket.id, LogAction.RECALLED, who=actor(ctx))
    _ticket_event(ctx, events.TICKET_RECALLED, ticket)
    return out(ticket)


@operation(
    "kitchen.ticket.cancel",
    kind="command",
    permission="kitchen.cancel_ticket",
    input=TicketCancelIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel number 12, they left",
                "void number 7 on the display, the bill stays as it is",
            ),
            "es": (
                "anula la comanda 12, se han ido",
                "cancela la comanda 7 aunque ya esté empezada",
            ),
        },
        "description": "Cancel a kitchen ticket that is still on the line, with an optional reason: it leaves the "
        "kitchen display and a void slip prints. The check in the till does not change.",
        "risk": "high",
    },
)
def cancel_ticket(ctx: OperationContext, data: TicketCancelIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    require(ticket, "cancel")
    alive = [
        item
        for item in _dishes(ticket)
        if item.status not in (*STRUCK, ItemStatus.SERVED)
    ]
    now = timezone.now()
    ticket.items.exclude(status__in=(ItemStatus.VOIDED, ItemStatus.SERVED)).update(
        status=ItemStatus.CANCELLED
    )
    ticket.status, ticket.cancelled_at = TicketStatus.CANCELLED, now
    ticket.save(update_fields=["status", "cancelled_at", "updated_at"])
    write_log(ticket.id, LogAction.CANCELLED, who=actor(ctx), notes=data.reason, at=now)
    _ticket_event(ctx, events.TICKET_CANCELLED, ticket, reason=data.reason)
    outcome = None
    if ticket.printed_at is not None:  # Only a round that went to paper gets its void slip (F22).
        outcome = print_ticket(
            ctx,
            ticket,
            alive,
            "cancel",
            title=str(CANCELLED_TICKET),
            negative=True,
            urgent=False,
        )
    return out(ticket, _error(outcome))


@operation(
    "kitchen.ticket.delete",
    kind="command",
    permission="kitchen.delete_ticket",
    input=TicketRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete the crew meal I made by hand",
                "remove the cancelled manual one, number 12",
            ),
            "es": (
                "borra la comanda que hice a mano para rehacer la ensalada",
                "elimina la comanda manual 12, ya anulada",
            ),
        },
        "description": "Delete a kitchen ticket made by hand that is to prepare or cancelled (one from a check is "
        "cancelled instead).",
        "risk": "high",
    },
)
def delete_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    if (
        data.ticket_id is not None
        and Ticket.objects.filter(pk=data.ticket_id, is_deleted=True).exists()
    ):
        return {"id": data.ticket_id}  # Deleted already: a repeated delete changes nothing.
    ticket = locked_ticket(data, settings)
    if ticket.order_id is not None or ticket.status not in (
        TicketStatus.PENDING,
        TicketStatus.CANCELLED,
    ):
        raise Conflict(str(NOT_DELETABLE), code="kitchen.ticket_not_deletable")
    ticket.is_deleted, ticket.deleted_at = True, timezone.now()
    ticket.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    write_log(ticket.id, LogAction.DELETED, who=actor(ctx))
    _ticket_event(ctx, events.TICKET_DELETED, ticket)
    return {"id": ticket.id}


@operation(
    "kitchen.ticket.set_rush",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRushIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "number 12 is in a hurry, rush it",
                "take the rush off number 7",
            ),
            "es": (
                "la 12 tiene prisa, ponla la primera",
                "la comanda 7 ya no es urgente",
            ),
        },
        "description": "Rush a ticket that is being cooked («table 4 is in a hurry»), or take the rush away: a rush "
        "jumps to the front of every display and prints a short notice where its dishes are still to do.",
        "risk": "normal",
    },
)
def set_rush(ctx: OperationContext, data: TicketRushIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    if ticket.status not in COOKING:
        raise Conflict(str(NOT_COOKING), code="kitchen.ticket_not_cooking")
    if ticket.priority == "vip":
        # A VIP ticket keeps its priority: a rush would demote it and taking it away would make it normal.
        raise Conflict(str(VIP_TICKET), code="kitchen.ticket_vip")
    if data.rush == (ticket.priority == "rush"):
        return out(ticket)
    print_error = None
    if data.rush:
        ticket.priority = "rush"
        ticket.rush_count += 1
        ticket.save(update_fields=["priority", "rush_count", "updated_at"])
        write_log(ticket.id, LogAction.RUSHED, who=actor(ctx))
        to_do = [item for item in _dishes(ticket) if item.status in TO_DO]
        print_error = _error(
            print_ticket(
                ctx, ticket, to_do, f"rush-{ticket.rush_count}", empty=True, urgent=True
            )
        )
    else:
        ticket.priority = "normal"
        ticket.save(update_fields=["priority", "updated_at"])
        write_log(ticket.id, LogAction.UNRUSHED, who=actor(ctx))
    _ticket_event(ctx, events.TICKET_UPDATED, ticket, priority=ticket.priority)
    return out(ticket, print_error)


@operation(
    "kitchen.ticket.reprint",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "reprint number 12 for the grill",
                "print another copy of number 7, the paper jammed",
            ),
            "es": (
                "reimprime la comanda 12",
                "la comanda 7 se ha roto, reimprímela",
            ),
        },
        "description": "Print a kitchen ticket again, as a copy, on its stations' printers.",
        "risk": "normal",
    },
)
def reprint_ticket(ctx: OperationContext, data: TicketRefIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    live = [item for item in _dishes(ticket) if item.status not in STRUCK]
    if not _paper(live):
        raise Conflict(str(NOTHING_ON_PAPER), code="kitchen.nothing_on_paper")
    ticket.reprint_count += 1
    ticket.save(update_fields=["reprint_count", "updated_at"])
    # A ticket that never went to paper (a round fired by Sales alone) prints as its first sheet.
    outcome = print_ticket(
        ctx,
        ticket,
        live,
        f"copy-{ticket.reprint_count}",
        duplicate=ticket.printed_at is not None,
    )
    if outcome is UNAVAILABLE:
        raise Conflict(str(PRINTING_UNAVAILABLE), code="kitchen.printing_unavailable")
    if isinstance(outcome, str):
        raise Conflict(str(PRINT_FAILED) % {"reason": outcome}, code="kitchen.print_failed")
    _went_to_paper(ticket, outcome)
    write_log(ticket.id, LogAction.REPRINTED, who=actor(ctx))
    _ticket_event(ctx, events.TICKET_REPRINTED, ticket)
    return out(ticket)
