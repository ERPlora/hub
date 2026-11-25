"""What a manager may approve, done by whoever may do it themselves, goes on the record of approvals (BASE-F85).

``LIVE["after_command"]`` calls :func:`note` inside every command's own transaction, once its body ran: the row is
applied with the command or not at all. What a pass let through, and what that asked of other apps on the way, is on the
record already (``base.approval.spend``). A person and an API key are noted, the platform and an automation are not. A
command that recorded no event did nothing (the answer given again to a request repeated with its key): neither is it.
"""

from live.context import OperationContext
from live.operations import Operation, pending_events
from ninja import Schema

from base.approvals import approval_of, figures_of, label_of
from base.services.approvals import note_own_right


def note(op: Operation, ctx: OperationContext, data: Schema) -> None:
    """Note ``op``, which just ran for ``ctx``, if a manager may approve it and whoever ran it needed no approval."""
    if label_of(op) is None or approval_of(ctx) is not None:
        return
    if getattr(ctx.actor, "is_authenticated", False) and pending_events():
        note_own_right(ctx, op, figures_of(op, data))
