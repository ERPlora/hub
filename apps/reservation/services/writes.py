"""What every write of the reservation app shares: the statuses by their short name and who acts."""

from live.context import OperationContext

from apps.reservation.models import ACTOR_MAX_LENGTH, Reservation

S = Reservation.Status


def actor_label(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:ACTOR_MAX_LENGTH]


def _stamp(row, ctx: OperationContext, *, created: bool = False) -> None:
    row.updated_by = actor_label(ctx)
    if created:
        row.created_by = row.updated_by
