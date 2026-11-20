"""What the worker writes in control while it makes a hub's database, and the leases it holds on each hub."""

import datetime as dt
import json
import logging
import os
import secrets
import socket
import time
from contextlib import contextmanager
from functools import partial
from uuid import UUID, uuid7

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from live.operations import atomic
from live.outbox import notify

from base import auth, registry, signing
from base.models import Hub
from base.tenancy import names as database_names
from base.tenancy.connections import control_name
from control.models import Cluster, HubDue, HubDump

logger = logging.getLogger(__name__)


# ── The provisioning's writes in control ───────────────────────────────────────────────────────────────────────────
#
# ``base.tenancy.provision`` makes a hub's database in steps; each step writes control here, in a short transaction of
# its own, never holding a row while the database is cloned or migrated. Who works on a hub holds its ``hub_due`` lease
# (``SELECT … FOR UPDATE SKIP LOCKED``, ``lease_until``), renewed at each step: two workers, or the worker and a
# command, never prepare the same hub at once.

#: The waits before a failed preparation is tried again: 1 min, 5 min, 15 min, then every hour.
PROVISION_RETRY_SECONDS = (60, 300, 900, 3600)
#: The longest error a failed preparation keeps (``Hub.last_error``).
LAST_ERROR_MAX = 2000


class ProvisioningStopped(Exception):
    """The hub left its preparation meanwhile (cancelled, its demo ended): nothing more is done for it."""


class ProvisioningFailed(Exception):
    """A step of a preparation that failed for a reason with a name (``no_cluster_available``,
    ``template_missing``…)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def retry_delay(attempts: int) -> dt.timedelta:
    """How long a preparation that failed ``attempts`` times waits before the next."""
    return dt.timedelta(seconds=PROVISION_RETRY_SECONDS[min(attempts, len(PROVISION_RETRY_SECONDS)) - 1])


@contextmanager
def _control_transaction():
    """A transaction of control's own (the registry's and ``hub_due``'s writes), whatever context the caller runs in
    (the worker, a command, an operation of the platform): ``live.operations.atomic`` on control's alias."""
    from base.tenancy.context import use_control

    with use_control(), atomic():
        yield


def ring(hub: Hub, at: dt.datetime | None = None, *, told: str) -> None:
    """``hub`` has work a business asked for (an app to set up, a reset) by ``at`` (now by default): due in ``hub_due``
    then, in the caller's transaction on control, and the worker told on the platform's channel after control's COMMIT
    (``base.control_pace``), so it does not wait for its look; ``told`` names what was asked."""
    HubDue.mark_due(hub, at)
    transaction.on_commit(partial(notify, registry.REGISTRY_SCOPE, [told]), robust=True)


def registry_row(hub_id: UUID) -> Hub | None:
    """The registry's row of ``hub_id``, its cluster with it, as it is now."""
    return Hub.objects.select_related("cluster").filter(pk=hub_id).first()


#: The statuses of a hub whose own database the worker serves (its outbox, its tasks): a ready one, and a business
#: that left but keeps its database, whose records still to send must reach the AEAT.
SERVED_STATUSES = (Hub.Status.READY, Hub.Status.CANCELLED, Hub.Status.ARCHIVING)


def hubs_to_serve(now: dt.datetime) -> list[Hub]:
    """The hubs with their own database the worker relays the outbox and runs the tasks of, each in its database, by
    id: ready ones and businesses that left but keep it (cancelled, being archived); never one being made, dropped or
    purged, a demo whose time is up, nor one moving to another cluster or being restored (its database is being
    copied)."""
    return list(
        Hub.objects.filter(status__in=SERVED_STATUSES)
        .exclude(registry.copying())
        .exclude(db_name="")
        .exclude(is_demo=True, expires_at__lte=now)
        .select_related("cluster")
        .order_by("id")
    )


def registry_row_by_slug(slug: str) -> Hub | None:
    """The registry's row of ``slug``, its cluster with it, as it is now (``seed_local_hubs``)."""
    return Hub.objects.select_related("cluster").filter(slug=slug).first()


#: This process's name on the leases it holds (``HubDue.lease_owner``): host, pid and a draw of its own.
LEASE_OWNER = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(4)}"


def _free(now: dt.datetime) -> Q:
    return Q(lease_until__isnull=True) | Q(lease_until__lte=now)


def _leased(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str) -> None:
    """Renew ``owner``'s lease of ``hub_id``; ``ProvisioningStopped`` when it is no longer ``owner``'s (it ran out and
    another worker took it): nothing more is written for it here."""
    if not HubDue.objects.filter(pk=hub_id, lease_owner=owner).update(lease_until=now + lease):
        raise ProvisioningStopped(f"the lease of {hub_id} is no longer {owner}'s: another worker holds it now.")


def _take(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str) -> None:
    HubDue.objects.filter(pk=hub_id).update(lease_until=now + lease, lease_owner=owner)


def claim_hub(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """Make ``hub_id`` due now and take its lease for ``owner`` (this process); ``None`` when someone else holds it
    (or no such hub)."""
    with _control_transaction():
        hub = Hub.objects.filter(pk=hub_id).first()
        if hub is None:
            return None
        HubDue.mark_due(hub, now)
        free = HubDue.objects.select_for_update(skip_locked=True).filter(_free(now), pk=hub_id).exists()
        if not free:
            return None
        _take(hub_id, now, lease, owner)
    return registry_row(hub_id)


def claim_next_due_hub(now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> UUID | None:
    """Take for ``owner`` the lease of the hub due longest by ``now`` that nobody holds: one at a time, right before
    it is worked on, so no lease runs out while it waits its turn in a pass. Never a ready hub's (a demo whose time is
    up aside): its ring is its apps' to set up (``base.worker_activations._activations``), which keep their own time, or its
    data work's, whose pass takes it."""
    with _control_transaction():
        due = (
            HubDue.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(_free(now), due_at__lte=now)
            .exclude(Q(hub__status=Hub.Status.READY) & ~Q(hub__is_demo=True, hub__expires_at__lte=now))
            .order_by("due_at")
            .values_list("hub_id", flat=True)
            .first()
        )
        if due is None:
            return None
        _take(due, now, lease, owner)
    return due


def release_hub(hub_id: UUID, now: dt.datetime, *, owner: str = LEASE_OWNER) -> None:
    """Give ``owner``'s lease of ``hub_id`` back: due again when it still has work (a retry, a demo to drop, a reset to
    do, the copy of a business that left: at its ``next_attempt_at`` when the last try failed), else gone: a business
    past its 90 days has no row here, :func:`claim_next_data_hub` finds it on the registry. A lease that is no longer
    ``owner``'s is left alone."""
    with _control_transaction():
        hub = Hub.objects.filter(pk=hub_id).first()
        due = HubDue.objects.select_for_update().filter(pk=hub_id, lease_owner=owner)
        if not due.exists():
            return
        if hub is not None and (
            hub.status == Hub.Status.FAILED or (hub.is_demo and hub.status == Hub.Status.DROPPING and hub.next_attempt_at)
        ):
            due.update(due_at=hub.next_attempt_at or now, lease_until=None, lease_owner="")
        elif hub is not None and (
            hub.status in registry.PREPARING_STATUSES
            or (hub.is_demo and hub.status in (Hub.Status.EXPIRED, Hub.Status.DROPPING))
            or hub.reset_requested_at is not None
        ):
            due.update(due_at=now, lease_until=None, lease_owner="")
        elif hub is not None and offboarding_due(hub):
            due.update(due_at=hub.next_attempt_at or now, lease_until=None, lease_owner="")
        else:
            due.delete()


def place_hub(hub_id: UUID) -> Hub:
    """Put ``hub_id`` on a cluster unless it is on one: the open one with the fewest hubs, under its ``max_hubs``.

    Without any ``Cluster`` row, the settings' own server (``cluster`` stays empty). With rows and none open with room,
    ``no_cluster_available``: never the settings' server then. The clusters are locked while it counts, so two
    placements at once never pass a limit.
    """
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        if hub.cluster_id is not None:
            return registry_row(hub_id)
        clusters = list(Cluster.objects.select_for_update().order_by("name"))
        if not clusters:
            return registry_row(hub_id)
        placed = dict(
            Hub.objects.filter(cluster__in=clusters)
            .exclude(status=Hub.Status.PURGED)
            .values_list("cluster")
            .annotate(count=Count("pk"))
        )
        # The hubs on their way to a cluster (``control.hub.move``), now or in their night, take their place there
        # already.
        for coming in ("moving_to", "move_scheduled_to"):
            for cluster_id, count in (
                Hub.objects.filter(**{f"{coming}__in": clusters}).values_list(coming).annotate(count=Count("pk"))
            ):
                placed[cluster_id] = placed.get(cluster_id, 0) + count
        room = [
            cluster
            for cluster in clusters
            if cluster.is_open and (cluster.max_hubs == 0 or placed.get(cluster.pk, 0) < cluster.max_hubs)
        ]
        if not room:
            raise ProvisioningFailed("no_cluster_available", "No open database cluster has room for a new hub.")
        hub.cluster = min(room, key=lambda cluster: (placed.get(cluster.pk, 0), cluster.name))
        hub.save(update_fields=["cluster", "updated_at"])
    return registry_row(hub_id)


def _preparing(hub_id: UUID, now: dt.datetime) -> Hub:
    hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").get(pk=hub_id)
    if hub.status not in registry.PREPARING_STATUSES or (hub.is_demo and registry.is_gone(hub, now)):
        raise ProvisioningStopped(f"{hub.slug} is {hub.status}: its preparation stops.")
    return hub


def provision_step(
    hub_id: UUID, status: str, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER
) -> Hub:
    """Note that ``hub_id`` is at the step ``status`` of its preparation and renew ``owner``'s lease;
    ``ProvisioningStopped`` when it left its preparation meanwhile or the lease is no longer ``owner``'s."""
    with _control_transaction():
        hub = _preparing(hub_id, now)
        _leased(hub_id, now, lease, owner)
        if hub.status != status:
            hub.status = status
            hub.save(update_fields=["status", "updated_at"])
    return hub


def provision_ready(  # noqa: PLR0913
    hub_id: UUID,
    now: dt.datetime,
    schema_apps: dict[str, str],
    *,
    tell_saas: bool = True,
    owner: str = LEASE_OWNER,
    seeded_version: int | None = None,
) -> Hub | None:
    """``hub_id`` is ready: its schema as the migrator left it; a business's SaaS hears it after the COMMIT (unless
    ``tell_saas`` is false: the local hubs). ``ProvisioningStopped`` if the lease is no longer ``owner``'s.

    ``seeded_version``: the version of the SaaS's photo its seeding applied. With its row locked (as
    :func:`hub_state_apply` locks it), a newer photo that came meanwhile, kept on the row only, means it is not ready
    yet: ``None``, and the seeding applies that one first."""
    with _control_transaction():
        hub = _preparing(hub_id, now)
        if not HubDue.objects.filter(pk=hub_id, lease_owner=owner).exists():
            raise ProvisioningStopped(f"the lease of {hub_id} is no longer {owner}'s: another worker holds it now.")
        if seeded_version is not None and hub.state_version != seeded_version:
            return None
        hub.status, hub.ready_at = Hub.Status.READY, now
        hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
        hub.schema_apps, hub.schema_state = schema_apps, Hub.SchemaState.CURRENT
        hub.save(
            update_fields=[
                "status",
                "ready_at",
                "attempts",
                "last_error",
                "next_attempt_at",
                "schema_apps",
                "schema_state",
                "updated_at",
            ]
        )
        if tell_saas and not hub.is_demo:
            # A demo's SaaS asks for it (``GET /internal/hubs/{id}``) and keeps no row to tell.
            transaction.on_commit(partial(report_ready, hub.id), robust=True)
    return hub


def provision_failed(hub_id: UUID, now: dt.datetime, error: str, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The preparation of ``hub_id`` failed with ``error``: ``failed``, tried again after :func:`retry_delay`.

    ``None`` when the hub left its preparation meanwhile, or its lease is no longer ``owner``'s: nothing is noted."""
    with _control_transaction():
        try:
            hub = _preparing(hub_id, now)
        except ProvisioningStopped:
            return None
        if not HubDue.objects.filter(pk=hub_id, lease_owner=owner).exists():
            return None
        hub.attempts += 1
        hub.status, hub.last_error = Hub.Status.FAILED, error[:LAST_ERROR_MAX]
        hub.next_attempt_at = now + retry_delay(hub.attempts)
        hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])
        HubDue.objects.filter(pk=hub_id).update(due_at=hub.next_attempt_at)
    return hub


def demo_dropping(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The demo ``hub_id``, which ended, is being dropped (``dropping``, its lease renewed); ``None`` if it is no demo
    that ended, was purged already, or whose last drop failed and waits for its ``next_attempt_at``.

    Its first drop starts its counters again: a preparation that had failed is no drop that failed."""
    with _control_transaction():
        hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=hub_id).first()
        if hub is None or not hub.is_demo or hub.status == Hub.Status.PURGED or not registry.is_gone(hub, now):
            return None
        if hub.status == Hub.Status.DROPPING and hub.next_attempt_at is not None and hub.next_attempt_at > now:
            return None
        _leased(hub_id, now, lease, owner)
        if hub.status != Hub.Status.DROPPING:
            hub.status = Hub.Status.DROPPING
            hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
            hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])
    return hub


def demo_drop_failed(hub_id: UUID, now: dt.datetime, error: str, *, owner: str = LEASE_OWNER) -> None:
    """The drop of the demo ``hub_id`` failed with ``error``: noted, and tried again after :func:`retry_delay` (its
    ``hub_due`` waits for it: never every tick). Nothing is noted once its lease is no longer ``owner``'s."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().filter(pk=hub_id, status=Hub.Status.DROPPING).first()
        if hub is None or not HubDue.objects.filter(pk=hub_id, lease_owner=owner).exists():
            return
        hub.attempts += 1
        hub.last_error = f"drop_failed: {error}"[:LAST_ERROR_MAX]
        hub.next_attempt_at = now + retry_delay(hub.attempts)
        hub.save(update_fields=["attempts", "last_error", "next_attempt_at", "updated_at"])
        HubDue.objects.filter(pk=hub_id).update(due_at=hub.next_attempt_at)


#: The path of the SaaS that hears a business is ready (``hubs/internal.py`` of the SaaS).
READY_PATH = "/internal/hubs/{id}/ready"


def report_ready(hub_id: UUID) -> None:
    """Tell the SaaS that ``hub_id`` is ready: ``POST {SAAS_INTERNAL_URL}/internal/hubs/{id}/ready``, signed v1 + v2.

    Called after the COMMIT that made it ready (:func:`provision_ready`, the worker's), never inside it. It never
    raises: a failure is logged and not retried, because the SaaS asks ``GET /internal/hubs/{id}`` about a sign-up
    without its ``ready`` two minutes later (``reconcile_hub_states``) and marks it itself.
    """
    path = READY_PATH.format(id=hub_id)
    body = json.dumps({"id": str(hub_id)}).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", path, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        status, _answer = auth.post(auth.saas_internal_url(path), body, headers, auth.TIMEOUT_SECONDS)
    except OSError as failed:
        logger.warning("base.hub.ready_unreported hub=%s: the SaaS is unreachable (%s).", hub_id, failed)
        return
    if 200 <= status < 300:
        logger.info("base.hub.ready_reported hub=%s", hub_id)
    else:
        logger.warning("base.hub.ready_unreported hub=%s: the SaaS answered %s.", hub_id, status)


def holds_hub_lease(hub_id: UUID, *, owner: str = LEASE_OWNER) -> bool:
    """Whether ``hub_id``'s lease is still ``owner``'s (this process's): run out or not, nobody else took it."""
    return HubDue.objects.filter(pk=hub_id, lease_owner=owner).exists()


def renew_hub_lease(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> None:
    """Renew ``owner``'s lease of the ready hub ``hub_id`` (a cut of it runs); ``ProvisioningStopped`` when it is no
    longer ``owner``'s."""
    with _control_transaction():
        _leased(hub_id, now, lease, owner)


def platform_hub_register(slug: str) -> Hub:
    """ERPlora's platform hub in the registry (``manage.py create_platform_hub``): its row, ``is_platform``, born
    ``requested`` with its own database's name, as a sign-up, but not due: the command makes it itself, under its
    lease, and the worker's pass over ``hub_due`` never takes it first. The one already there otherwise. Never a
    business's row: the slug is reserved (``live.slugs``)."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().filter(slug=slug).first()
        if hub is not None:
            return hub
        new_id = uuid7()
        hub = Hub.objects.create(
            id=new_id,
            slug=slug,
            status=Hub.Status.REQUESTED,
            db_name=database_names.hub_db_name(control_name(), new_id),
            is_platform=True,
        )
    return registry_row(hub.id)


def offboarding_due(hub: Hub) -> bool:
    """Whether ``hub`` left with a finished database of its own and has no copy of this leaving yet."""
    return bool(
        hub.status == Hub.Status.CANCELLED
        and hub.db_name
        and hub.ready_at is not None
        and hub.cancelled_at is not None
        and not HubDump.objects.filter(
            hub_id=hub.pk, kind=HubDump.Kind.OFFBOARDING, created_at__gte=hub.cancelled_at
        ).exists()
    )
