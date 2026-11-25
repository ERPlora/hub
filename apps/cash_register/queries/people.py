"""How the drawer names who acts in an operation, as a colleague reads them."""

from live.context import OperationContext

from apps.cash_register.models import ACTOR_MAX_LENGTH
from base.queries.people import actor_name


def actor(ctx: OperationContext) -> str:
    """Who acts, as a colleague reads them (never by their address); the system's own label."""
    return actor_name(ctx.actor)[:ACTOR_MAX_LENGTH]
