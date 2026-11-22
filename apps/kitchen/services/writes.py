"""What every write of the kitchen shares: who acts, the locks, the numbers of the day, the History, the
events of a ticket and the logger.
"""

import logging

from django.db.models import F
from django.utils import timezone
from live.context import OperationContext
from live.outbox import record_event

from apps.kitchen.models import ACTOR_MAX_LENGTH, DayCounter, KitchenSettings, Station, Ticket
from apps.kitchen.queries.reads import EPOCH

# One logger for every module of the kitchen's writes, named after the package rather than each module.
logger = logging.getLogger("apps.kitchen.services")


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH] if ctx.actor is not None else ""


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


def write_log(  # noqa: PLR0913
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
