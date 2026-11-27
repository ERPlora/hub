"""Paper (KITCHEN-F08, F09, F14, F17, F22, F29): the sheets of a ticket queued in Printing, the void slips, the
pass and the sheet of a round.
"""

from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, OperationError
from live.operations import UnknownOperation, get

from apps.kitchen import allergy
from apps.kitchen.models import Destination, KitchenSettings, OrderType, Ticket
from apps.kitchen.queries.reads import STRUCK
from apps.inventory.models import Unit
from apps.kitchen.services.writes import logger
from base.business import paper_time
from base.queries.people import without_address
from base.queries.catalog_images import business_language

URGENT = _("!! URGENT !!")
VOIDED_DISH = _("VOIDED DISH · %(label)s")
CANCELLED_TICKET = _("CANCELLED · %(label)s")

#: What ``_print`` answers when Printing is off or absent: no paper, and nobody waits for it.
UNAVAILABLE = object()


def _print(  # noqa: PLR0913
    ctx: OperationContext,
    *,
    key: str,
    document: dict,
    usage: str,
    printer: str,
    ref: str,
):
    """Queue a ``kitchen_order`` in Printing: ``None`` when queued; ``UNAVAILABLE`` without Printing, or when no
    printer is given and no active one prints ``usage`` (the kitchen cooks from its screen: nothing waits for paper);
    else why Printing refused it. Nested in this write, it runs in a savepoint: a refusal leaves nothing behind."""
    try:
        op, printers = get("printing.job.create"), get("printing.printer.list")
    except UnknownOperation:
        return UNAVAILABLE
    data = {
        "job_key": key[:128],
        "document_type": "kitchen_order",
        "document": document,
        "usage": usage,
        "printer": printer or None,
        "source_app": "kitchen",
        "source_ref": ref[:64],
    }
    of_its_function = printers.input.model_validate({"usage": usage, "is_active": True, "limit": 1})
    try:
        if not printer and not printers(ctx, of_its_function).total:
            return UNAVAILABLE
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
        if item.destination not in (Destination.PRINTER, Destination.BOTH):
            continue
        sheets.setdefault((item.printer_usage, item.printer_name), []).append(item)
    return sheets


def _quantity(value) -> float:
    return float(Decimal(value).normalize())


def _sheet(  # noqa: PLR0913
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
        "waiter": without_address(ticket.waiter),
        "priority": str(URGENT) if rush else "",
        "duplicate": duplicate,
        "time": paper_time(timezone.now() if negative else ticket.received_at),
        "items": [_paper_dish(item, negative) for item in items],
    }


def _paper_dish(item, negative: bool) -> dict:
    """A dish as the printer paints it (``render_kitchen_order`` of the app): one sold by measure with its unit
    («0.35 kg»), the dishes of a menu in a run under its header (``combo_ref``, ``combo_name``), its options one line
    each and then its note."""
    quantity = _quantity(item.quantity)
    dish = {"name": item.name, "quantity": -quantity if negative else quantity}
    if item.unit and item.unit != Unit.UNIT:
        dish["unit"] = item.unit
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
    language = business_language(ctx)
    for (usage, printer), dishes in _paper(items).items():
        shown = [] if sheet.get("empty") else dishes
        document = _sheet(ticket, shown, **{k: v for k, v in sheet.items() if k != "empty"})
        document = allergy.on_paper(document, shown, language)
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
