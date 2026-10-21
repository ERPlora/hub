"""Write operations of the kitchen app: one operation = one transaction, with its events in the outbox and
its line in the History.

Every write that touches a ticket starts by **settling** (``settle``): it locks the settings row (so every
write of the kitchen of a business goes one after the other: two cooks at once never step on each
other), saves the rounds Sales fired that the kitchen has not saved yet (no relay in phase 1,
queries.py) and saves what Sales did to the tickets (``queries.effective``), with its History at the
moment it happened, its events and its void slips. Then the operation finds its ticket, already saved.

Paper goes through Printing's operation by its name (``printing.job.create``), in a savepoint of the same
transaction: Printing off or absent is no paper and no error; any other refusal comes back in
``print_error`` and never undoes the kitchen's action (KITCHEN-F08).
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound, OperationError
from live.operations import UnknownOperation, get, operation
from live.outbox import record_event

from apps.inventory.models import Category, Product
from apps.inventory.queries import held
from apps.kitchen import events
from apps.kitchen.models import (
    ACTOR_MAX_LENGTH,
    CategoryRoute,
    DayCounter,
    Destination,
    ItemStatus,
    KitchenSettings,
    LogAction,
    OrderType,
    ProductRoute,
    Station,
    Ticket,
    TicketItem,
    TicketStatus,
)
from apps.kitchen.queries import (
    COOKING,
    EPOCH,
    IN_FLIGHT,
    MAX_CANDIDATES,
    STATION_NOT_FOUND,
    STRUCK,
    TICKET_NOT_FOUND,
    TO_DO,
    Change,
    TicketView,
    business_day,
    category_routes,
    current_settings,
    effective,
    find_scope,
    find_station,
    find_ticket_view,
    in_progress_by_station,
    in_scope,
    pending_rounds,
    person_label,
    product_routes,
    round_view,
    routing,
    saved_views,
    settings_out,
    station_map,
    station_row,
    ticket_out,
)
from apps.kitchen.schemas import (
    DeletedOut,
    ItemBumpIn,
    ItemRecallIn,
    ReceivedOut,
    RouteOut,
    RoutingClearIn,
    RoutingSetIn,
    SettingsOut,
    SettingsPatchIn,
    StationIn,
    StationOut,
    StationPatchIn,
    StationRefIn,
    SyncOut,
    TicketCancelIn,
    TicketCreateIn,
    TicketOut,
    TicketReceiveIn,
    TicketRefIn,
    TicketRushIn,
    TicketSendIn,
    TicketSyncIn,
)
from apps.sale.models import OrderLine

logger = logging.getLogger(__name__)

INVALID_TRANSITION = _(
    "That kitchen ticket is no longer in the state this action requires. Refresh and try again."
)
NOT_COOKING = _("That ticket is no longer being cooked.")
VIP_TICKET = _("That ticket is VIP: a rush does not change its priority.")
NOT_DELETABLE = _(
    "That ticket cannot be deleted: it comes from a check or it is already being cooked. Cancel it instead."
)
ITEM_NOT_IN_TICKET = _("That dish is not on this ticket.")
NOTHING_ON_PAPER = _(
    "Nothing of this ticket goes to paper: its stations are screen only."
)
NOTHING_TO_COOK = _("Nothing on this check is cooked: services do not go to the kitchen.")
PRINTING_UNAVAILABLE = _("Printing is not active in this business.")
PRINT_FAILED = _("The ticket could not be printed: %(reason)s")
STATION_NAME_TAKEN = _(
    "There is already a station with that name. Choose a different name."
)
STATION_IN_USE = _(
    "This station cannot be deleted: products or categories are routed to it, or it has dishes to cook. "
    "Move them to another station first."
)
STATION_INACTIVE = _(
    "That station is switched off: switch it on or choose another one."
)
PRODUCT_NOT_FOUND = _("That product does not exist in the catalogue.")
PRODUCT_AMBIGUOUS = _("“%(said)s” matches several products: %(names)s. Say which one.")
CATEGORY_NOT_FOUND = _("That category does not exist in the catalogue.")
CATEGORY_AMBIGUOUS = _(
    "“%(said)s” matches several categories: %(names)s. Say which one."
)
ROUTE_NOT_FOUND = _("Nothing is routed from that product or category.")
AMBER_FIRST = _("The amber warning has to come before the red one.")
URGENT = _("!! URGENT !!")
VOIDED_DISH = _("VOIDED DISH · %(label)s")
CANCELLED_TICKET = _("CANCELLED · %(label)s")

#: The steps of a ticket: action → the statuses it may start from.
ALLOWED = {
    "start": (TicketStatus.PENDING,),
    "ready": COOKING,
    "serve": (TicketStatus.READY,),
    "recall": (TicketStatus.READY,),
    "cancel": IN_FLIGHT,
}

#: What ``_print`` answers when Printing is off or absent: no paper, and nobody waits for it.
UNAVAILABLE = object()


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH] if ctx.actor is not None else ""


# ── Settling: the rounds Sales fired and what it did after ───────────────────────────────────────


def locked_settings() -> KitchenSettings:
    """The settings row, locked: every write of the kitchen goes one after the other (made again,
    receiving everything, if it was lost), and so does the Hub admin's «Delete» of a station (admin.py), so a
    route, a dish or a line of the History never names a station deleted meanwhile."""
    row, _created = KitchenSettings.objects.select_for_update().get_or_create(
        singleton=True, defaults={"receiving_since": EPOCH}
    )
    return row


def locked_row(model: type[Station] | type[Ticket], pk) -> Station | Ticket | None:
    """The live row ``pk``, read again and locked until this write commits; ``None`` when it was deleted after
    it was found. The Hub admin's «Delete» of a ticket and its change page («is deleted» ticked) do not go in
    line with the kitchen's writes: one that came between the read and the lock is not found, as one deleted
    before."""
    return model.objects.select_for_update().filter(pk=pk, is_deleted=False).first()


def take_number(day) -> int:
    """The next number of the business day ``day`` (``fiscal_counter`` style: no gaps, no sequences)."""
    counter, _created = DayCounter.objects.select_for_update().get_or_create(day=day)
    counter.last_number = F("last_number") + 1
    counter.save(update_fields=["last_number"])
    counter.refresh_from_db(fields=["last_number"])
    return counter.last_number


def write_log(
    ticket_id,
    action: str,
    *,
    who: str = "",
    notes: str = "",
    at=None,
    item_id=None,
    station_id=None,
):
    from apps.kitchen.models import LogEntry

    return LogEntry.objects.create(
        ticket_id=ticket_id,
        action=action,
        actor=who,
        notes=notes[:255],
        created_at=at or timezone.now(),
        item_id=item_id,
        station_id=station_id,
    )


def _ticket_event(ctx: OperationContext, name: str, ticket: Ticket, **more) -> None:
    record_event(
        ctx, name, {"ticket_id": str(ticket.id), "number": ticket.number, **more}
    )


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
    record_event(
        ctx,
        events.TICKET_RECEIVED,
        {
            "ticket_id": str(ticket.id),
            "number": ticket.number,
            "order_id": str(ticket.order_id),
            "round_no": ticket.round_no,
        },
    )
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


def settle(ctx: OperationContext, settings: KitchenSettings) -> tuple[int, int]:
    """Save the rounds not saved yet (in the order of their numbers) and what Sales did to the tickets on
    the line. Returns ``(rounds saved, tickets changed)``."""
    rounds = pending_rounds(settings)
    if rounds:
        route = routing()
        for rnd in rounds:
            save_round(ctx, rnd, route)
    changed = 0
    on_the_line = Ticket.objects.filter(
        is_deleted=False, status__in=IN_FLIGHT
    ).prefetch_related("items")
    for view in saved_views(on_the_line):
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


# ── Paper (KITCHEN-F08, F09, F14, F17, F22, F29) ─────────────────────────────────────────────────


def _print(
    ctx: OperationContext,
    *,
    key: str,
    document: dict,
    usage: str,
    printer: str,
    ref: str,
):
    """Queue a ``kitchen_order`` in Printing: ``None`` when queued, ``UNAVAILABLE`` without Printing, else why
    Printing refused it. Nested in this write, it runs in a savepoint: a refusal leaves nothing behind."""
    try:
        op = get("printing.job.create")
    except UnknownOperation:
        return UNAVAILABLE
    data = {
        "job_key": key[:128],
        "document_type": "kitchen_order",
        "document": document,
        "usage": usage,
        "source_app": "kitchen",
        "source_ref": ref[:64],
    }
    if printer:
        data["printer"] = printer
    try:
        op(ctx, op.input.model_validate(data))
    except AppInactive:
        return UNAVAILABLE
    except OperationError as refused:
        return refused.message
    return None


def _paper(items) -> dict[tuple[str, str], list]:
    """The dishes that go to paper, one sheet per printer (function and given printer)."""
    sheets: dict[tuple[str, str], list] = {}
    for item in items:
        if (
            item.destination != Destination.PRINTER
            and item.destination != Destination.BOTH
        ):
            continue
        sheets.setdefault((item.printer_usage, item.printer_name), []).append(item)
    return sheets


def _quantity(value) -> float:
    return float(Decimal(value).normalize())


def _sheet(
    ticket: Ticket,
    items,
    *,
    title: str = "",
    negative: bool = False,
    urgent: bool | None = None,
    duplicate=False,
) -> dict:
    label = ticket.label or str(OrderType(ticket.order_type).label)
    rush = ticket.priority == "rush" if urgent is None else urgent
    return {
        "order_number": ticket.number,
        "round_number": ticket.round_no,
        "table": title % {"label": label} if title else ticket.label,
        "label": title % {"label": label} if title else label,
        "waiter": ticket.waiter,
        "priority": str(URGENT) if rush else "",
        "duplicate": duplicate,
        "items": [_paper_dish(item, negative) for item in items],
    }


def _paper_dish(item, negative: bool) -> dict:
    """A dish as the printer paints it (``render_kitchen_order`` of the app): the dishes of a menu in a run
    under its header (``combo_ref``, ``combo_name``), its options one line each and then its note."""
    quantity = _quantity(item.quantity)
    dish = {"name": item.name, "quantity": -quantity if negative else quantity}
    if item.menu_dish:
        dish |= {"combo_ref": str(item.sale_line_id), "combo_name": item.menu_name}
    if item.modifiers:
        dish["modifiers"] = list(item.modifiers)
    if item.notes:
        dish["notes"] = item.notes
    return dish


def print_ticket(
    ctx: OperationContext, ticket: Ticket, items, key: str, **sheet
) -> object:
    """One sheet per printer of ``items`` (the ones that go to paper); the first refusal, if any."""
    outcome = UNAVAILABLE
    for (usage, printer), dishes in _paper(items).items():
        document = _sheet(
            ticket,
            [] if sheet.get("empty") else dishes,
            **{k: v for k, v in sheet.items() if k != "empty"},
        )
        result = _print(
            ctx,
            key=f"kitchen-{ticket.id}-{key}-{usage}-{printer}",
            document=document,
            usage=usage,
            printer=printer,
            ref=ticket.number,
        )
        if result is None and outcome is UNAVAILABLE:
            outcome = None
        elif isinstance(result, str) and not isinstance(outcome, str):
            outcome = result
    return outcome


def _error(outcome) -> str | None:
    return outcome if isinstance(outcome, str) else None


def _void_slip(
    ctx: OperationContext, ticket: Ticket, items, *, key: str, title
) -> None:
    if ticket.printed_at is None:
        return  # Nothing of it went to paper: there is no sheet to void (KITCHEN-F22, F29).
    outcome = print_ticket(
        ctx, ticket, items, key, title=str(title), negative=True, urgent=False
    )
    if isinstance(outcome, str):
        logger.warning(
            "kitchen: the void slip of %s was not printed: %s", ticket.number, outcome
        )


def _dishes(ticket: Ticket):
    return list(ticket.items.all())


# ── Receiving and sending rounds (KITCHEN-F05, F18) ──────────────────────────────────────────────


def _round_ticket(line_ids) -> Ticket | None:
    """The ticket of the round of ``line_ids``, locked until the end of the write; none if it was never saved
    or was deleted since."""
    ticket_id = (
        TicketItem.objects.filter(sale_line_id__in=list(line_ids))
        .values_list("ticket_id", flat=True)
        .first()
    )
    return locked_row(Ticket, ticket_id) if ticket_id is not None else None


def _enrich(
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


def _went_to_paper(ticket: Ticket, outcome) -> None:
    """Its sheet is queued: from now on a void slip or a copy has something to answer to."""
    if outcome is None and ticket.printed_at is None:
        ticket.printed_at = timezone.now()
        ticket.save(update_fields=["printed_at", "updated_at"])


def _print_round(ctx: OperationContext, ticket: Ticket) -> str | None:
    live = [item for item in _dishes(ticket) if item.status not in STRUCK]
    outcome = print_ticket(ctx, ticket, live, "order")
    _went_to_paper(ticket, outcome)
    return _error(outcome)


@operation(
    "kitchen.ticket.send",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketSendIn,
    output=TicketOut,
    expose_api=True,
    ai={
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
        waiter=person_label(ctx.actor),
    )
    return out(ticket, _print_round(ctx, ticket))


@operation(
    "kitchen.ticket.receive",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketReceiveIn,
    output=ReceivedOut,
    ai={
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


# ── A ticket by hand (KITCHEN-F23) ───────────────────────────────────────────────────────────────


def _one(rows, said: str, missing, ambiguous, code: str):
    if not rows:
        raise NotFound(str(missing), code=f"kitchen.{code}_not_found")
    if len(rows) > 1:
        names = ", ".join(row.name for row in rows[:MAX_CANDIDATES])
        raise Conflict(
            str(ambiguous) % {"said": said, "names": names},
            code=f"kitchen.{code}_ambiguous",
        )
    return rows[0]


def find_product(product_id: UUID | None, said: str | None) -> Product:
    products = Product.objects.filter(is_deleted=False)
    if product_id is not None:
        return _one(
            list(products.filter(pk=product_id)),
            str(product_id),
            PRODUCT_NOT_FOUND,
            PRODUCT_AMBIGUOUS,
            "product",
        )
    exact = list(products.filter(name__iexact=said)[:2]) or list(
        products.filter(sku__iexact=said)[:2]
    )
    rows = exact or list(
        products.filter(name__icontains=said).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    return _one(rows, said, PRODUCT_NOT_FOUND, PRODUCT_AMBIGUOUS, "product")


def find_category(category_id: UUID | None, said: str | None) -> Category:
    categories = Category.objects.filter(is_deleted=False)
    if category_id is not None:
        return _one(
            list(categories.filter(pk=category_id)),
            str(category_id),
            CATEGORY_NOT_FOUND,
            CATEGORY_AMBIGUOUS,
            "category",
        )
    exact = list(categories.filter(name__iexact=said)[:2])
    rows = exact or list(
        categories.filter(name__icontains=said).order_by("name", "id")[
            : MAX_CANDIDATES + 1
        ]
    )
    return _one(rows, said, CATEGORY_NOT_FOUND, CATEGORY_AMBIGUOUS, "category")


@operation(
    "kitchen.ticket.create",
    kind="command",
    permission="kitchen.add_ticket",
    input=TicketCreateIn,
    output=TicketOut,
    expose_api=True,
    ai={
        "description": "Make a kitchen ticket by hand, with no check (a staff meal, a dish to remake): its type, "
        "where it goes, notes and its dishes (products of the catalogue by name, or free text), each to its station.",
        "risk": "normal",
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
        waiter=person_label(ctx.actor)[:ACTOR_MAX_LENGTH],
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


# ── The journey of a ticket (KITCHEN-F13, F17, F21) ──────────────────────────────────────────────


def _pass(
    ctx: OperationContext, ticket: Ticket, settings: KitchenSettings
) -> str | None:
    """The pass on paper when a ticket turns ready, if the settings ask for it (KITCHEN-F17)."""
    if not settings.print_pass:
        return None
    live = [item for item in _dishes(ticket) if item.status not in STRUCK]
    return _error(
        print_ticket(
            ctx, ticket, live, f"pass-{ticket.ready_at:%Y%m%d%H%M%S%f}", urgent=False
        )
    )


@operation(
    "kitchen.ticket.start",
    kind="command",
    permission="kitchen.change_ticket",
    input=TicketRefIn,
    output=TicketOut,
    expose_api=True,
    ai={
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
        raise Conflict(
            str(PRINT_FAILED) % {"reason": outcome}, code="kitchen.print_failed"
        )
    _went_to_paper(ticket, outcome)
    write_log(ticket.id, LogAction.REPRINTED, who=actor(ctx))
    _ticket_event(ctx, events.TICKET_REPRINTED, ticket)
    return out(ticket)


# ── The dishes (KITCHEN-F11, F12) ────────────────────────────────────────────────────────────────


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


# ── Stations (KITCHEN-F01 to F03) ────────────────────────────────────────────────────────────────


def _locked_station(data: StationRefIn) -> Station:
    """The station ``data`` names, locked until the end of the write (not found if deleted since it was found)."""
    station = locked_row(Station, find_station(data.station_id, data.station).pk)
    if station is None:
        raise NotFound(str(STATION_NOT_FOUND), code="kitchen.station_not_found")
    return station


def _station_out(station: Station) -> dict:
    routes = product_routes(station=station).count() + category_routes(station=station).count()
    in_progress = in_progress_by_station(current_settings()).get(station.id, 0)
    return station_row(station, in_progress, routes)


def _name_free(name: str, but=None) -> None:
    taken = Station.objects.filter(is_deleted=False, name__iexact=name)
    if but is not None:
        taken = taken.exclude(pk=but.pk)
    if taken.exists():
        raise Conflict(str(STATION_NAME_TAKEN), code="kitchen.station_name_taken")


def _save_station(station: Station, **save) -> None:
    try:
        with transaction.atomic():
            station.save(**save)
    except IntegrityError:
        raise Conflict(
            str(STATION_NAME_TAKEN), code="kitchen.station_name_taken"
        ) from None


@operation(
    "kitchen.station.create",
    kind="command",
    permission="kitchen.manage_station",
    input=StationIn,
    output=StationOut,
    expose_api=True,
    ai={
        "description": "Create a kitchen station (grill, bar, desserts) with its colour, whether it goes to the "
        "screen, to paper or both, and its printer (the kitchen or bar function, or a printer by its name).",
        "risk": "normal",
    },
)
def create_station(ctx: OperationContext, data: StationIn) -> dict:
    _name_free(data.name)
    station = Station(**data.model_dump(), created_by=actor(ctx), updated_by=actor(ctx))
    _save_station(station)
    record_event(ctx, events.STATION_CREATED, {"station_id": str(station.id)})
    return _station_out(station)


@operation(
    "kitchen.station.update",
    kind="command",
    permission="kitchen.manage_station",
    input=StationPatchIn,
    output=StationOut,
    expose_api=True,
    ai={
        "description": "Change a station, named by its id or its name: its name, colour, destination, printer, "
        "position, or switch it off (new dishes then go by their category, or to no station).",
        "risk": "normal",
    },
)
def update_station(ctx: OperationContext, data: StationPatchIn) -> dict:
    # What was sent keeps the station it went to: the rounds not saved yet are saved first.
    begin(ctx)
    station = _locked_station(data)
    changes = data.model_dump(exclude_unset=True, exclude={"station_id", "station"})
    changes = {name: value for name, value in changes.items() if value is not None}
    if "name" in changes:
        _name_free(changes["name"], but=station)
    for name, value in changes.items():
        setattr(station, name, value)
    station.updated_by = actor(ctx)
    _save_station(station)
    record_event(ctx, events.STATION_UPDATED, {"station_id": str(station.id)})
    return _station_out(station)


@operation(
    "kitchen.station.delete",
    kind="command",
    permission="kitchen.manage_station",
    input=StationRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a station (it leaves the lists; the tickets already sent keep its name). Refused while "
        "products or categories are routed to it or it has dishes to cook.",
        "risk": "high",
    },
)
def delete_station(ctx: OperationContext, data: StationRefIn) -> dict:
    settings = begin(ctx)
    station = _locked_station(data)
    routed = product_routes(station=station).exists() or category_routes(station=station).exists()
    busy = in_progress_by_station(settings).get(station.id, 0) > 0
    if routed or busy:
        raise Conflict(str(STATION_IN_USE), code="kitchen.station_in_use")
    station.is_deleted, station.deleted_at = True, timezone.now()
    station.updated_by = actor(ctx)
    station.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
    record_event(ctx, events.STATION_DELETED, {"station_id": str(station.id)})
    return {"id": station.id}


# ── Routing (KITCHEN-F04) ────────────────────────────────────────────────────────────────────────


def _held(model, row, missing, code: str):
    """``row`` read again, live and held until this write commits (``held``): Inventory's «Delete» or the
    Hub admin's waits for the write, and one deleted since it was found is not found, as one deleted
    before."""
    live = held(model.objects.filter(pk=row.pk, is_deleted=False))
    if not live:
        raise NotFound(str(missing), code=f"kitchen.{code}_not_found")
    return live[0]


def _target(data) -> tuple[Product | None, Category | None]:
    if data.product_id is not None or data.product:
        return find_product(data.product_id, data.product), None
    return None, find_category(data.category_id, data.category)


def _route_of(product: Product | None, category: Category | None):
    """The route of ``product`` or of ``category`` (or none), locked."""
    routes = (
        ProductRoute.objects.filter(product=product)
        if product
        else CategoryRoute.objects.filter(category=category)
    )
    return routes.select_for_update(of=("self",)).select_related("station").first()


def _route_out(
    product: Product | None, category: Category | None, station: Station
) -> dict:
    target = product or category
    return {
        "kind": "product" if product else "category",
        "target_id": target.id,
        "target_name": target.name,
        "station_id": station.id,
        "station_name": station.name,
    }


def _route_event(ctx: OperationContext, station: Station, product, category) -> None:
    record_event(
        ctx,
        events.ROUTING_CHANGED,
        {
            "station_id": str(station.id),
            "product_id": str(product.id) if product else None,
            "category_id": str(category.id) if category else None,
        },
    )


@operation(
    "kitchen.routing.set",
    kind="command",
    permission="kitchen.manage_station",
    input=RoutingSetIn,
    output=RouteOut,
    expose_api=True,
    ai={
        "description": "Send a product or a category of the catalogue to a station («drinks go to the bar»), "
        "replacing where it went before. Only the rounds sent from now on follow it.",
        "risk": "normal",
    },
)
def set_route(ctx: OperationContext, data: RoutingSetIn) -> dict:
    # Only the rounds sent from now on follow it: the ones not saved yet are saved first.
    begin(ctx)
    station = find_station(data.station_id, data.station)
    if not station.is_active:
        raise Conflict(str(STATION_INACTIVE), code="kitchen.station_inactive")
    product, category = _target(data)
    # The route it replaces is locked before its product or category is held: the Hub admin's «Delete» of a
    # product or a category takes its route first and the row last, so neither waits for the other in a circle.
    _route_of(product, category)
    if product is not None:
        product = _held(Product, product, PRODUCT_NOT_FOUND, "product")
    else:
        category = _held(Category, category, CATEGORY_NOT_FOUND, "category")
    who = actor(ctx)
    if product is not None:
        ProductRoute.objects.update_or_create(
            product=product, defaults={"station": station, "updated_by": who}
        )
    else:
        CategoryRoute.objects.update_or_create(
            category=category, defaults={"station": station, "updated_by": who}
        )
    _route_event(ctx, station, product, category)
    return _route_out(product, category, station)


@operation(
    "kitchen.routing.clear",
    kind="command",
    permission="kitchen.manage_station",
    input=RoutingClearIn,
    output=RouteOut,
    expose_api=True,
    ai={
        "description": "Take away where a product or a category goes: from now on it goes by its category, or to no "
        "station.",
        "risk": "normal",
    },
)
def clear_route(ctx: OperationContext, data: RoutingClearIn) -> dict:
    begin(ctx)
    product, category = _target(data)
    # Locked, not held: taking a route away names nothing, and the Hub admin's «Delete» of its product or
    # category (which takes the route first) waits for it, or took it already and it is not found.
    route = _route_of(product, category)
    if route is None:
        raise NotFound(str(ROUTE_NOT_FOUND), code="kitchen.route_not_found")
    station = route.station
    route.delete()
    _route_event(ctx, station, product, category)
    return _route_out(product, category, station)


# ── Settings (KITCHEN-F26) ───────────────────────────────────────────────────────────────────────


@operation(
    "kitchen.settings.update",
    kind="command",
    permission="kitchen.change_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change the kitchen display settings (only what is sent): the clock, the amber and red minutes, "
        "the sound and its tone and volume, the pass on paper, whether the kitchen works from the screen, the "
        "default ticket type.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    row = locked_settings()
    # What the settings in force already decide (a round served by paper) is saved before they change:
    # switching the screen back on never brings a charged round back «To prepare».
    settle(ctx, row)
    sent = {
        name: value
        for name, value in data.model_dump(exclude_unset=True).items()
        if value is not None
    }
    warning = sent.get("warning_minutes", row.warning_minutes)
    critical = sent.get("critical_minutes", row.critical_minutes)
    if warning >= critical:
        fields = {
            name: str(AMBER_FIRST)
            for name in ("warning_minutes", "critical_minutes")
            if name in sent
        }
        raise InvalidPayload(str(AMBER_FIRST), code="invalid_field", fields=fields)
    changed = sorted(
        name for name, value in sent.items() if getattr(row, name) != value
    )
    if "works_from_screen" in changed:
        row.screen_changed_at = timezone.now()
    for name in changed:
        setattr(row, name, sent[name])
    row.updated_by = actor(ctx)
    row.save()
    if changed:
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": changed})
    return settings_out(row)

