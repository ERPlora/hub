"""A business that leaves: its copy, its final copy and its purge (``base.hub.purge``).

``base.hub.cancel`` makes a business with a finished database of its own due; the worker copies it once
(``offboarding``) and the database stays (its 90 days; ``restore`` brings it back). A copy that fails is tried again
at ``next_attempt_at`` (1 min, 5 min, 15 min, then every hour), with ``attempts`` and ``last_error`` on the row.
After its 90 days (``base.tenancy.offboarding``) ``archiving`` makes its final copy,
``dropping`` drops its database and ``base.hub.purge`` leaves the row as a tombstone.
"""

import datetime as dt
from collections.abc import Iterable
from uuid import UUID

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base import events, registry
from base.models import Hub, Membership, SessionOwner
from base.registry import hub_answer, internal_only
from base.schemas import HubGetIn, HubOut
from base.services.hub_registry import LEFT_STATUSES, _locked_hub
from base.services.provisioning import (
    LAST_ERROR_MAX,
    LEASE_OWNER,
    _control_transaction,
    _free,
    _leased,
    _take,
    claim_hub,
    retry_delay,
)
from base.services.reset import _holds
from base.services.sessions import _end_sessions
from control.models import HubDue, HubDump

#: How long a business that left keeps its database.
OFFBOARDING_RETENTION = dt.timedelta(days=90)
#: How long a business kept for its fiscal documents waits before it is looked at again.
FISCAL_HOLD_RECHECK = dt.timedelta(days=1)


def _offboarding_copied(hub_ref, cancelled_at) -> Exists:
    return Exists(
        HubDump.objects.filter(hub_id=hub_ref, kind=HubDump.Kind.OFFBOARDING, created_at__gte=cancelled_at)
    )


def past_retention(hub: Hub, now: dt.datetime) -> bool:
    """Whether ``hub`` is a business on its way out after its 90 days, ``now``: left that long ago, or already
    ``archiving`` or ``dropping``. Never a demo (their own way out: ``base.tenancy.provision``), the platform's hub, nor
    one moving to another cluster or being restored (its database is being copied). Its ``next_attempt_at`` says when,
    not whether."""
    if hub.is_demo or hub.is_platform or registry.is_copying(hub):
        return False
    if hub.status in (Hub.Status.ARCHIVING, Hub.Status.DROPPING):
        return True
    return (
        hub.status == Hub.Status.CANCELLED
        and hub.cancelled_at is not None
        and hub.cancelled_at <= now - OFFBOARDING_RETENTION
    )


def _next_past_retention(now: dt.datetime) -> UUID | None:
    """The business longest past its 90 days whose next attempt came and whose lease nobody holds: :func:`past_retention`,
    as a query, on the registry. They have no ``hub_due`` row until one is taken: due all at once, the pass over
    ``hub_due`` would take them too, only to give them back."""
    return (
        Hub.objects.filter(
            Q(status=Hub.Status.CANCELLED, cancelled_at__lte=now - OFFBOARDING_RETENTION)
            | Q(status__in=(Hub.Status.ARCHIVING, Hub.Status.DROPPING)),
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),
            is_demo=False,
            is_platform=False,
        )
        .exclude(registry.copying())
        .exclude(Exists(HubDue.objects.filter(pk=OuterRef("pk"), lease_until__gt=now)))
        .order_by("cancelled_at", "id")
        .values_list("id", flat=True)
        .first()
    )


def claim_next_data_hub(now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> UUID | None:
    """Take for ``owner`` the lease of the hub due longest by ``now``, that nobody holds, with data work to do: a reset
    asked, or the copy of a business that left; with none, a business past its 90 days."""
    leaving = (
        Q(hub__status=Hub.Status.CANCELLED, hub__ready_at__isnull=False, hub__cancelled_at__isnull=False)
        & ~Q(hub__db_name="")
        & ~_offboarding_copied(OuterRef("hub_id"), OuterRef("hub__cancelled_at"))
    )
    with _control_transaction():
        due = (
            HubDue.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(_free(now), due_at__lte=now)
            .filter(Q(hub__reset_requested_at__isnull=False) | leaving)
            .order_by("due_at")
            .values_list("hub_id", flat=True)
            .first()
        )
        if due is not None:
            _take(due, now, lease, owner)
            return due
        leaving_for_good = _next_past_retention(now)
    if leaving_for_good is None or claim_hub(leaving_for_good, now, lease, owner=owner) is None:
        return None
    return leaving_for_good


def offboarding_copy_failed(hub_id: UUID, now: dt.datetime, error: str, *, owner: str = LEASE_OWNER) -> None:
    """The copy (or, after its 90 days, the drop) of a business that left failed: tried again at its next attempt.
    One that came back meanwhile has nothing to note."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _holds(hub_id, owner, timezone.now())
        if hub.status not in (*LEFT_STATUSES, Hub.Status.DROPPING):
            return
        hub.attempts += 1
        hub.last_error = error[:2000]
        hub.next_attempt_at = now + retry_delay(hub.attempts)
        hub.save(update_fields=["attempts", "last_error", "next_attempt_at", "updated_at"])


def offboarding_copied(hub_id: UUID) -> None:
    """The copy of a business that left was kept: nothing more to try."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(attempts=0, last_error="", next_attempt_at=None, updated_at=timezone.now())


def _next_step_out(
    hub_id: UUID, status: str, now: dt.datetime, lease: dt.timedelta, owner: str
) -> Hub | None:
    """``hub_id``, past its 90 days, moves to ``status`` (its lease renewed, its counters from zero when it changes);
    ``None`` when it is no longer on its way out: it came back, or moved."""
    with _control_transaction():
        hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=hub_id).first()
        if hub is None or not past_retention(hub, now):
            return None
        _leased(hub_id, now, lease, owner)
        if hub.status != status:
            hub.status = status
            hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
            hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])
    return hub


def offboarding_archiving(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The final copy of the business ``hub_id`` is being made (``archiving``: it can still come back)."""
    return _next_step_out(hub_id, Hub.Status.ARCHIVING, now, lease, owner)


def offboarding_dropping(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The database of the business ``hub_id`` is going (``dropping``: from here it never comes back)."""
    return _next_step_out(hub_id, Hub.Status.DROPPING, now, lease, owner)


def offboarding_held(hub_id: UUID, now: dt.datetime, apps: Iterable[str], *, owner: str = LEASE_OWNER) -> None:
    """The business ``hub_id`` keeps fiscal documents (``apps``' own) that nothing archives yet: its database stays and
    it stays ``cancelled``, looked at again after :data:`FISCAL_HOLD_RECHECK`. Its 90 days are not counted again."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _holds(hub_id, owner, timezone.now())
        if hub.status not in LEFT_STATUSES:
            return
        hub.status = Hub.Status.CANCELLED
        hub.attempts = 0
        hub.last_error = f"fiscal_archive_missing: {', '.join(apps)}"[:LAST_ERROR_MAX]
        hub.next_attempt_at = now + FISCAL_HOLD_RECHECK
        hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])


def final_copy_kept(hub: Hub) -> bool:
    """Whether the copy of ``hub`` made after its 90 days is already kept (a drop that failed needs no second one)."""
    return HubDump.objects.filter(
        hub_id=hub.pk, kind=HubDump.Kind.OFFBOARDING, created_at__gte=hub.cancelled_at + OFFBOARDING_RETENTION
    ).exists()


# Not an assistant tool: the worker's last step of a business past its 90 days, no person.
@operation("base.hub.purge", kind="command", permission=None, input=HubGetIn, output=HubOut, ai=INTERNAL)
def hub_purge(ctx: OperationContext, data: HubGetIn) -> dict:
    """The database and the files of the business ``data.id`` went (``base.tenancy.offboarding``): its people lose their
    way in and the row stays ``purged`` as a tombstone (its host answers 410, forever), with nothing of the business on
    it: no name, no photo. Its cluster is let go, or a tombstone would keep that cluster from ever being deleted.

    Rows only, in one transaction of control. One that is not ``dropping`` is ``base.hub_not_dropping`` (a demo has
    ``base.demo.purge``); one already purged stays as it is."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    if hub.status == Hub.Status.PURGED:
        return hub_answer(hub)
    if hub.is_demo or hub.status != Hub.Status.DROPPING:
        raise Conflict(gettext("This business is not being dropped."), code="base.hub_not_dropping")
    Membership.objects.filter(host=hub.slug).delete()
    _end_sessions(SessionOwner.objects.filter(host=hub.slug))
    hub.status, hub.purged_at = Hub.Status.PURGED, timezone.now()
    hub.name, hub.state, hub.reset_sections, hub.cluster = "", {}, None, None
    hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
    hub.save(
        update_fields=[
            "status",
            "purged_at",
            "name",
            "state",
            "reset_sections",
            "cluster",
            "attempts",
            "last_error",
            "next_attempt_at",
            "updated_at",
        ]
    )
    record_event(ctx, events.HUB_PURGED, {"id": str(hub.id), "slug": hub.slug})
    return hub_answer(hub)
