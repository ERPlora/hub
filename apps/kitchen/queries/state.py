"""What Sales did after (KITCHEN-F27, F28, F29): a line voided, the check voided or charged, applied when read,
without writing; and the tickets still in flight.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import replace
from uuid import UUID

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.kitchen.models.fields import Destination
from apps.kitchen.models.settings import KitchenSettings
from apps.kitchen.models.tickets import ItemStatus, Ticket, TicketItem, TicketStatus
from apps.kitchen.queries.reads import EPOCH, IN_FLIGHT, STRUCK
from apps.kitchen.queries.rounds import unsaved_views
from apps.kitchen.queries.views import Change, TicketView, saved_views
from apps.sale.models.orders import Order, OrderLine


def _latest(moments: Iterable[dt.datetime | None]) -> dt.datetime:
    known = [moment for moment in moments if moment is not None]
    return max(known) if known else timezone.now()


def _cancel(view: TicketView, at: dt.datetime) -> None:
    view.status = TicketStatus.CANCELLED
    view.cancelled_at = at
    for item in view.items:
        if item.status not in (ItemStatus.VOIDED, ItemStatus.SERVED):
            item.status = ItemStatus.CANCELLED


def _serve(view: TicketView, at: dt.datetime) -> None:
    view.status = TicketStatus.SERVED
    view.served_at = at
    view.ready_at = view.ready_at or at
    for item in view.items:
        if not item.struck:
            item.status = ItemStatus.SERVED
            item.ready_at = item.ready_at or at


def effective(  # noqa: C901
    view: TicketView, settings: KitchenSettings
) -> tuple[TicketView, list[Change]]:
    """The ticket as it stands after what Sales did to its lines and checks, and what changed.

    In order: a line voided in the till strikes its dish (F29) — the round with nothing alive left is
    cancelled, with only ready dishes left it goes to the pass —; every check of its lines voided
    cancels it (F28); every check charged in full (F27) serves it when it was ready before the charge,
    or when nobody marks it on a screen (every dish to paper only, or the kitchen on paper since before
    the charge). A ticket made by hand, or already served or cancelled, never changes here.
    """
    if view.status not in IN_FLIGHT or not any(item.facts for item in view.items):
        return view, []
    view = replace(view, items=[replace(item) for item in view.items])
    changes: list[Change] = []

    voided = [
        item
        for item in view.items
        if item.facts
        and item.facts.removed_at
        and item.status not in (*STRUCK, ItemStatus.SERVED)
    ]
    for item in voided:
        item.status = ItemStatus.VOIDED
        item.void_reason = item.facts.void_reason
        changes.append(
            Change("item_voided", item.facts.removed_at, item.id, item.void_reason)
        )
    if voided:
        at = _latest(item.facts.removed_at for item in voided)
        live = view.live_items
        if not live:
            _cancel(view, at)
            changes.append(Change("cancelled", at))
            return view, changes
        if view.status != TicketStatus.READY and all(
            item.status == ItemStatus.READY for item in live
        ):
            view.status = TicketStatus.READY
            view.ready_at = at
            view.started_at = view.started_at or at
            changes.append(Change("ready", at))

    linked = [item for item in view.live_items if item.facts]
    statuses = {item.facts.order_status for item in linked}
    if not linked or len(statuses) != 1:
        return view, changes
    closed = _latest(item.facts.order_closed_at for item in linked)
    if statuses == {Order.Status.VOIDED}:
        _cancel(view, closed)
        changes.append(Change("cancelled", closed))
    elif statuses == {Order.Status.COMPLETED}:
        if view.status == TicketStatus.READY:
            if view.ready_at is not None and view.ready_at <= closed:
                _serve(view, closed)
                changes.append(Change("served", closed))
        elif all(
            item.destination == Destination.PRINTER for item in view.live_items
        ) or (
            not settings.works_from_screen
            and closed >= (settings.screen_changed_at or EPOCH)
        ):
            _serve(view, closed)
            changes.append(Change("served", closed))
    return view, changes


def in_flight_views(
    settings: KitchenSettings, order_ids: Iterable[UUID] | None = None
) -> list[TicketView]:
    """Every ticket the kitchen holds as on the line (saved, or a round not saved yet), as Sales left it
    (``effective``): some of them may be served or cancelled by now."""
    saved = Ticket.objects.filter(
        is_deleted=False, status__in=IN_FLIGHT
    ).prefetch_related("items")
    if order_ids is not None:
        lines = OrderLine.objects.filter(order_id__in=list(order_ids)).values("id")
        saved = saved.filter(
            Exists(
                TicketItem.objects.filter(ticket=OuterRef("pk"), sale_line_id__in=lines)
            )
        )
    views = saved_views(saved) + unsaved_views(settings, order_ids)
    return [effective(view, settings)[0] for view in views]
