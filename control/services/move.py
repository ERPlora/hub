"""Moving a ready hub's own database to another cluster: asked now or for the business's next night, or
cancelled."""

import datetime as dt

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.business import zone_of
from control import events, queries
from control.models.hubs import Cluster, Hub
from control.schemas import MOVE_AT_NIGHT, HubIdIn, HubMoveIn, HubMoveOut
from control.services.actor import platform_admin_only
from control.services.clusters import _locked, living_hubs

#: When a move asked for the night may start, on the business's own clock: Square's nightly updates run at 03:00, after
#: the bars close and before the bakeries open. It bounds the start, as AWS's maintenance window does, not the end.
NIGHT_STARTS = dt.time(3)
NIGHT_ENDS = dt.time(5)


def night_start(now: dt.datetime, zone: dt.tzinfo) -> dt.datetime:
    """When a move asked at ``now`` for the night of a business on ``zone`` starts: ``now`` inside its window, else
    the next :data:`NIGHT_STARTS` on that clock."""
    local = now.astimezone(zone)
    if NIGHT_STARTS <= local.time() < NIGHT_ENDS:
        return now
    day = local.date() if local.time() < NIGHT_STARTS else local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(day, NIGHT_STARTS, tzinfo=zone)


def _move_refused(message: str, code: str) -> Conflict:
    return Conflict(message, code=code)


def _room_for_one_more(cluster: Cluster, besides: Hub) -> bool:
    """Whether ``cluster`` takes ``besides`` too: its living hubs and the others on their way there, now or in their
    night, under its limit."""
    if cluster.max_hubs == 0:
        return True
    coming = Hub.objects.filter(Q(moving_to=cluster) | Q(move_scheduled_to=cluster)).exclude(pk=besides.pk)
    return living_hubs(cluster).count() + coming.count() < cluster.max_hubs


def _scheduled_move_refused() -> Conflict:
    return _move_refused(
        gettext("This hub already has a move asked for the night: cancel it first."), "control.hub_move_scheduled"
    )


def _movable(hub: Hub, target: Cluster) -> None:
    """Refuse (``Conflict``) unless the ready ``hub`` moves to ``target`` now: what a move asked now checks, and a move
    asked for the night checks again when the worker starts it."""
    if hub.status != Hub.Status.READY or not hub.db_name:
        raise _move_refused(
            gettext("Only a ready hub with a database of its own moves."), "control.hub_not_movable"
        )
    if hub.is_demo:
        raise _move_refused(gettext("A demo does not move: it ends on its own."), "control.hub_is_demo")
    if hub.moving_to_id is not None:
        raise _move_refused(gettext("This hub is already moving."), "control.hub_moving")
    if hub.restoring_from_id is not None:
        raise _restoring()
    if hub.cluster_id == target.pk:
        raise _move_refused(gettext("This hub is on that cluster already."), "control.hub_already_there")
    if not target.is_open:
        raise _move_refused(gettext("That cluster is closed to new hubs."), "control.cluster_closed")
    if not _room_for_one_more(target, hub):
        raise _move_refused(gettext("That cluster has no room for another hub."), "control.cluster_full")
    if hub.db_name not in queries.measure(hub.cluster, [hub.db_name]):
        raise _move_refused(
            gettext("The database of this hub is not on its server: there is nothing to move."),
            "control.hub_database_missing",
        )


def _move_answer(hub: Hub) -> dict:
    return {
        "id": hub.pk,
        "slug": hub.slug,
        "cluster": hub.cluster_id,
        "moving_to": hub.moving_to_id,
        "scheduled_to": hub.move_scheduled_to_id,
        "scheduled_for": hub.move_scheduled_for,
    }


# Not an assistant tool: the platform's admins, in the Hub admin («Move to cluster…»).
@operation("control.hub.move", kind="command", permission=None, input=HubMoveIn, output=HubMoveOut, ai=INTERNAL)
def hub_move(ctx: OperationContext, data: HubMoveIn) -> dict:
    """Ask the worker to move the ready hub ``data.hub``'s own database to the cluster ``data.cluster``: now, or in the
    business's next night (``data.when``)."""
    platform_admin_only(ctx)
    hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=data.hub).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    target = _locked(data.cluster)
    if hub.move_scheduled_to_id is not None:
        raise _scheduled_move_refused()
    _movable(hub, target)
    origin = str(hub.cluster_id) if hub.cluster_id else ""
    hub.last_error = ""
    if data.when == MOVE_AT_NIGHT:
        hub.move_scheduled_to = target
        hub.move_scheduled_for = night_start(timezone.now(), zone_of(hub.timezone))
        hub.save(update_fields=["move_scheduled_to", "move_scheduled_for", "last_error", "updated_at"])
        at = hub.move_scheduled_for.astimezone(dt.UTC).isoformat()
        payload = {"id": str(hub.pk), "slug": hub.slug, "from": origin, "to": str(target.pk), "at": at}
        record_event(ctx, events.HUB_MOVE_SCHEDULED, payload)
        return _move_answer(hub)
    hub.moving_to = target
    hub.save(update_fields=["moving_to", "last_error", "updated_at"])
    record_event(
        ctx, events.HUB_MOVE_REQUESTED, {"id": str(hub.pk), "slug": hub.slug, "from": origin, "to": str(target.pk)}
    )
    return _move_answer(hub)


# Not an assistant tool: the platform's admins, in the Hub admin («Cancel the move»).
@operation(
    "control.hub.move_cancel", kind="command", permission=None, input=HubIdIn, output=HubMoveOut, ai=INTERNAL
)
def hub_move_cancel(ctx: OperationContext, data: HubIdIn) -> dict:
    """Ask the worker to undo the move of ``data.id``, started or not: the hub is marked (``move_undo_asked_at``) and the
    worker puts it back on its origin. No note of a copy is made nor taken here: an older copy of the same hub on its
    server is never taken for its data. A move asked for the night that has not started is just taken away: nothing
    was closed."""
    platform_admin_only(ctx)
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    if hub.moving_to_id is None and hub.move_scheduled_to_id is not None:
        target = hub.move_scheduled_to_id
        hub.move_scheduled_to, hub.move_scheduled_for = None, None
        hub.save(update_fields=["move_scheduled_to", "move_scheduled_for", "updated_at"])
        record_event(
            ctx, events.HUB_SCHEDULED_MOVE_CANCELLED, {"id": str(hub.pk), "slug": hub.slug, "to": str(target)}
        )
        return _move_answer(hub)
    if hub.moving_to_id is None:
        raise _move_refused(gettext("This hub is not moving."), "control.hub_not_moving")
    hub.move_undo_asked_at = timezone.now()
    hub.last_error = "move_cancelled: the move was cancelled in the Hub admin."
    hub.save(update_fields=["move_undo_asked_at", "last_error", "updated_at"])
    record_event(ctx, events.HUB_MOVE_CANCEL_REQUESTED, {"id": str(hub.pk), "slug": hub.slug})
    return _move_answer(hub)


def _restoring() -> Conflict:
    return _move_refused(gettext("This hub is being restored from a copy."), "control.hub_restoring")
