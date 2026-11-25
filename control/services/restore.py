"""Putting a ready hub's database back as it was at a moment, or making a separate copy of it, from its copy on a
temporary cluster."""

import uuid

from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.tenancy import names
from base.tenancy.connections import control_name
from control import events, queries
from control.models import Cluster, Hub, RestoredCopy
from control.schemas import HubRestoreIn, HubRestoreOut, RestoredCopyOut
from control.services.actor import _who, platform_admin_only
from control.services.clusters import _locked, living_hubs
from control.services.move import _move_refused, _restoring


def _copy_to_restore(hub: Hub, source: Cluster) -> None:
    """Refuse unless the copy of ``hub``'s database is on ``source`` under its name, of any size."""
    if hub.db_name not in queries.measure(source, [hub.db_name]):
        raise _move_refused(
            gettext("The hub's database is not on that cluster: there is no copy to restore it from."),
            "control.restore_copy_missing",
        )


def _restorable(data: HubRestoreIn) -> tuple[Hub, Cluster]:
    """The ready hub ``data.hub`` and the temporary cluster ``data.cluster``, both locked, when a copy of its database
    as it was at ``data.at`` can be taken from that cluster: what a restore in place and a copy aside both ask."""
    hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=data.hub).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    source = _locked(data.cluster)
    if hub.status != Hub.Status.READY or not hub.db_name:
        raise _move_refused(
            gettext("Only a ready hub with a database of its own is restored."), "control.hub_not_restorable"
        )
    if hub.is_demo:
        raise _move_refused(gettext("A demo is not restored: it ends on its own."), "control.hub_is_demo")
    if hub.moving_to_id is not None:
        raise _move_refused(gettext("This hub is already moving."), "control.hub_moving")
    if hub.restoring_from_id is not None:
        raise _restoring()
    if hub.cluster_id == source.pk:
        raise _move_refused(
            gettext("The copy comes from a temporary cluster restored to that moment, never from the hub's own."),
            "control.restore_from_own_cluster",
        )
    if source.is_open:
        raise _move_refused(
            gettext("A copy is restored only from a cluster closed to new hubs: a temporary one."),
            "control.cluster_open",
        )
    if living_hubs(source).exists():
        raise _move_refused(
            gettext("Hubs live on that cluster: the copy comes from a temporary one with none."),
            "control.cluster_holds_hubs",
        )
    if data.at > timezone.now():
        message = gettext("That moment has not come yet.")
        raise InvalidPayload(message, code="control.restore_point_ahead", fields={"at": message})
    _copy_to_restore(hub, source)
    return hub, source


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.hub.restore", kind="command", permission=None, input=HubRestoreIn, output=HubRestoreOut, ai=INTERNAL
)
def hub_restore(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Ask the worker to put the ready hub ``data.hub``'s database back as it was at ``data.at``, from its copy on the
    temporary cluster ``data.cluster``."""
    platform_admin_only(ctx)
    hub, source = _restorable(data)
    hub.restoring_from = source
    hub.restore_point = data.at
    hub.last_error = ""
    hub.save(update_fields=["restoring_from", "restore_point", "last_error", "updated_at"])
    record_event(
        ctx,
        events.HUB_RESTORE_REQUESTED,
        {"id": str(hub.pk), "slug": hub.slug, "from": str(source.pk), "at": data.at.isoformat()},
    )
    return {
        "id": hub.pk,
        "slug": hub.slug,
        "cluster": hub.cluster_id,
        "restoring_from": source.pk,
        "restore_point": data.at,
    }


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.hub.restore_aside",
    kind="command",
    permission=None,
    input=HubRestoreIn,
    output=RestoredCopyOut,
    ai=INTERNAL,
)
def hub_restore_aside(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Ask the worker for a separate copy of the ready hub ``data.hub``'s database as it was at ``data.at``, from its
    copy on the temporary cluster ``data.cluster``, made on the hub's own cluster; the hub is not touched."""
    platform_admin_only(ctx)
    hub, source = _restorable(data)
    copy_id = uuid.uuid7()
    copy = RestoredCopy.objects.create(
        id=copy_id,
        hub=hub,
        cluster=hub.cluster,
        source=source,
        restore_point=data.at,
        db_name=names.copy_db_name(control_name(), copy_id),
        asked_by=_who(ctx),
    )
    record_event(
        ctx,
        events.HUB_RESTORE_ASIDE_REQUESTED,
        {
            "id": str(copy.pk),
            "hub": str(hub.pk),
            "slug": hub.slug,
            "from": str(source.pk),
            "at": data.at.isoformat(),
            "database": copy.db_name,
        },
    )
    return {
        "id": copy.pk,
        "hub": hub.pk,
        "slug": hub.slug,
        "db_name": copy.db_name,
        "cluster": copy.cluster_id,
        "source": source.pk,
        "restore_point": data.at,
        "status": copy.status,
    }
