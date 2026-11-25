"""Who acted on a method or a payment, as a colleague reads them: the name kept on what they did."""

from live.context import OperationContext

from apps.payment.models import ACTOR_MAX_LENGTH
from base.queries.people import actor_name


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a colleague reads them (never by their address); the platform or an API key as they name
    themselves."""
    return actor_name(ctx.actor)[:ACTOR_MAX_LENGTH]
