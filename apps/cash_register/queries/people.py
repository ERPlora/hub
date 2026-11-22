"""How the drawer names who acts in an operation, as a person reads them."""

from live.context import OperationContext


def actor(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:128]
