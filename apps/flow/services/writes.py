"""What the writes of Automations share: who acts, the messages more than one of them says and how long a
call or a turn of the assistant holds its run."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

DISABLED = _("This automation is paused: turn it on to run it.")
GRANT_BEYOND_CALLER = _("You cannot allow what you may not do yourself: «%(name)s».")

#: How long a call that left holds its run: after it, a call that never answered is sent again, with the
#: same key (at least once; the old hub's 5 minutes).
CALL_LEASE_MINUTES = 5


def _actor(ctx: OperationContext) -> str:
    return "" if ctx.actor is None else str(ctx.actor)[:128]
