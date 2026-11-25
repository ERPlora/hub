"""Who runs control's commands: the platform or one of its admins in the Hub admin, and the name a change is
recorded with."""

from live.context import OperationContext

from base.registry import internal_only


def platform_admin_only(ctx: OperationContext) -> None:
    """The platform, or one of its admins in the Hub admin (staff and superuser); support and customers are refused."""
    actor = ctx.actor
    if getattr(actor, "is_staff", False) and getattr(actor, "is_superuser", False):
        return
    internal_only(ctx)


def _who(ctx: OperationContext) -> str:
    """Who changes the switch, as the Hub admin shows it: the staff member's name (or username), or the platform."""
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:150]
    return str(actor)[:150]
