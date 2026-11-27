"""What every write of the reservation app shares: the statuses by their short name and who acts."""

from live.context import OperationContext

from apps.reservation.models import ACTOR_MAX_LENGTH, Reservation
from base.queries.people import actor_name

S = Reservation.Status


def actor_label(ctx: OperationContext) -> str:
    return actor_name(ctx.actor)[:ACTOR_MAX_LENGTH]


def _stamp(row, ctx: OperationContext, *, created: bool = False) -> None:
    row.updated_by = actor_label(ctx)
    if created:
        row.created_by = row.updated_by
