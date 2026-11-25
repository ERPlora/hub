"""Freezing the platform for a database upgrade, or lifting its freeze."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from control import events, queries
from control.models.freeze import Freeze
from control.schemas import FreezeIn, FreezeOut
from control.services.actor import _who, platform_admin_only


# Not an assistant tool: the platform's admins, in the Hub admin (Admin › Freeze).
@operation("control.freeze.set", kind="command", permission=None, input=FreezeIn, output=FreezeOut, ai=INTERNAL)
def freeze_set(ctx: OperationContext, data: FreezeIn) -> dict:
    """Freeze the platform for a database upgrade (``data.frozen``, with why) or lift its freeze; asked while already
    so, it is left as it is."""
    platform_admin_only(ctx)
    row = Freeze.objects.select_for_update().first()
    if row is None:
        # Control's migration makes it; only a database whose rows were emptied by hand lacks it. One row at most: a
        # second made at the same time is refused by its constraint, and this call fails rather than write twice.
        row = Freeze.objects.create()
    if row.frozen == data.frozen:
        return queries.freeze_answer(row)
    now = timezone.now()
    if data.frozen:
        row.frozen, row.reason, row.since, row.by = True, data.reason, now, _who(ctx)
        record_event(ctx, events.FREEZE_STARTED, {"reason": row.reason})
    else:
        started = row.since
        row.frozen, row.reason, row.since, row.by = False, "", now, _who(ctx)
        record_event(ctx, events.FREEZE_LIFTED, {"frozen_since": started.isoformat() if started else ""})
    row.save(update_fields=["frozen", "reason", "since", "by"])
    return queries.freeze_answer(row)
