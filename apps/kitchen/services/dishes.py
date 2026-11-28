"""The dishes (KITCHEN-F11, F12): bumping and recalling them."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.kitchen import events
from apps.kitchen.models.history import LogAction
from apps.kitchen.models.tickets import ItemStatus, Ticket, TicketItem, TicketStatus
from apps.kitchen.queries.reads import IN_FLIGHT, STRUCK, TO_DO
from apps.kitchen.queries.scope import find_scope, in_scope
from apps.kitchen.schemas.tickets import ItemBumpIn, ItemRecallIn, TicketOut
from apps.kitchen.services.paper import _pass
from apps.kitchen.services.settling import INVALID_TRANSITION, begin, locked_ticket, out
from apps.kitchen.services.writes import _ticket_event, actor, write_log

ITEM_NOT_IN_TICKET = _("That dish is not on this ticket.")


def _targets(ticket: Ticket, data: ItemBumpIn, statuses) -> list[TicketItem]:
    items = list(ticket.items.select_for_update().order_by("position", "id"))
    wanted = set(data.item_ids)
    if wanted - {item.id for item in items}:
        raise Conflict(str(ITEM_NOT_IN_TICKET), code="kitchen.item_not_in_ticket")
    scope = find_scope(data.station)
    return [
        item
        for item in items
        if (not wanted or item.id in wanted)
        and in_scope(item, scope)
        and item.status in statuses
    ]


@operation(
    "kitchen.item.bump",
    kind="command",
    permission="kitchen.change_ticket",
    input=ItemBumpIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "the fries for number 2 are done",
                "the grill has finished the steaks",
            ),
            "es": (
                "ya están las hamburguesas de la 4",
                "marca como hechas las patatas de la plancha",
            ),
        },
        "description": "Mark dishes ready: some of a ticket, or all of it on one station («the burgers of table 4 "
        "are ready», «grill is done with ticket 12»). The first one starts the ticket; with nothing left to do it "
        "goes to the pass. A dish already ready stays as it is.",
        "risk": "normal",
    },
)
def bump_items(ctx: OperationContext, data: ItemBumpIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    if ticket.status not in IN_FLIGHT:
        raise Conflict(str(INVALID_TRANSITION), code="kitchen.invalid_transition")
    targets = _targets(ticket, data, TO_DO)
    if not targets:
        return out(ticket)
    now, who = timezone.now(), actor(ctx)
    if ticket.status == TicketStatus.PENDING:
        ticket.status, ticket.started_at = TicketStatus.PREPARING, now
        write_log(ticket.id, LogAction.STARTED, who=who, at=now)
        _ticket_event(ctx, events.TICKET_STARTED, ticket)
    TicketItem.objects.filter(pk__in=[item.id for item in targets]).update(
        status=ItemStatus.READY, ready_at=now
    )
    for item in targets:
        write_log(
            ticket.id,
            LogAction.ITEM_READY,
            who=who,
            at=now,
            item_id=item.id,
            station_id=item.station_id,
        )
    record_event(
        ctx,
        events.ITEM_BUMPED,
        {"ticket_id": str(ticket.id), "item_ids": [str(item.id) for item in targets]},
    )
    print_error = None
    if (
        not ticket.items.exclude(status__in=STRUCK)
        .exclude(status=ItemStatus.READY)
        .exists()
    ):
        ticket.status, ticket.ready_at = TicketStatus.READY, now
        write_log(ticket.id, LogAction.READY, who=who, at=now)
        _ticket_event(ctx, events.TICKET_READY, ticket)
        ticket.save(update_fields=["status", "started_at", "ready_at", "updated_at"])
        print_error = _pass(ctx, ticket, settings)
    else:
        ticket.save(update_fields=["status", "started_at", "updated_at"])
    return out(ticket, print_error)


@operation(
    "kitchen.item.recall",
    kind="command",
    permission="kitchen.change_ticket",
    input=ItemRecallIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "the steak for number 4 isn't done after all, bring it back",
                "I marked the fries done by mistake, put them back to do",
            ),
            "es": (
                "las patatas de la 2 no estaban hechas, recupéralas",
                "me he equivocado con la hamburguesa de la 4: déjala otra vez pendiente",
            ),
        },
        "description": "Bring back dishes marked ready by mistake (some, or all of a ticket on one station); a ticket "
        "at the pass goes back to preparing. A dish still to do stays as it is.",
        "risk": "normal",
    },
)
def recall_items(ctx: OperationContext, data: ItemRecallIn) -> dict:
    settings = begin(ctx)
    ticket = locked_ticket(data, settings)
    if ticket.status not in IN_FLIGHT:
        raise Conflict(str(INVALID_TRANSITION), code="kitchen.invalid_transition")
    targets = _targets(ticket, data, (ItemStatus.READY,))
    if not targets:
        return out(ticket)
    who = actor(ctx)
    if ticket.status == TicketStatus.READY:
        ticket.status, ticket.ready_at = TicketStatus.PREPARING, None
        ticket.save(update_fields=["status", "ready_at", "updated_at"])
        write_log(ticket.id, LogAction.RECALLED, who=who)
        _ticket_event(ctx, events.TICKET_RECALLED, ticket)
    TicketItem.objects.filter(pk__in=[item.id for item in targets]).update(
        status=ItemStatus.PREPARING, ready_at=None
    )
    for item in targets:
        write_log(
            ticket.id,
            LogAction.ITEM_RECALLED,
            who=who,
            item_id=item.id,
            station_id=item.station_id,
        )
    record_event(
        ctx,
        events.ITEM_RECALLED,
        {"ticket_id": str(ticket.id), "item_ids": [str(item.id) for item in targets]},
    )
    return out(ticket)
