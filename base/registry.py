"""What the Hub reads of its registry of hubs (``base.Hub``) outside an operation (plan 2026-10-17, §1.2).

The host gate (``base.middleware.HubHostRequiredMiddleware``) runs before any operation, so it reads the row of the
Host's slug here: no row is 404, a hub that is gone 410, one still being prepared 503. The apps ask through
``base.operations.is_demo_hub``, never here. Reads only, one indexed lookup by slug each; no cache in phase 1 (a
cache would delay the 410 of an expired demo). The writes are the operations of ``base.services``.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import PermissionDenied

from control.models import Hub
from base.schemas import HubOut

#: The scope of the registry's operations (``base.hub.*``): the platform's, never a hub's.
REGISTRY_SCOPE = Scope("platform", "registry")

#: The statuses of a hub that ended (its way out included: a business archived and dropped, a demo dropped): its host
#: answers 410.
GONE_STATUSES = frozenset(
    {Hub.Status.CANCELLED, Hub.Status.ARCHIVING, Hub.Status.EXPIRED, Hub.Status.DROPPING, Hub.Status.PURGED}
)
#: The statuses of a hub still being prepared (its database made, its schema checked, its sign-up seeded, or a failed
#: step waiting for its retry; PLAN-DB §6): its host answers 503 and asks to try again.
PREPARING_STATUSES = frozenset(
    {Hub.Status.REQUESTED, Hub.Status.CREATING, Hub.Status.MIGRATING, Hub.Status.SEEDING, Hub.Status.FAILED}
)


def hub_by_slug(slug: str) -> Hub | None:
    """The registry's row of ``slug``, or ``None``."""
    return Hub.objects.filter(slug=slug).first()


def hub_id(slug: str) -> uuid.UUID | None:
    """The id of ``slug``'s row, or ``None``."""
    return Hub.objects.filter(slug=slug).values_list("id", flat=True).first()


def is_demo(slug: str) -> bool:
    """Whether ``slug`` names a demo hub of the registry (a slug without a row is no demo)."""
    return Hub.objects.filter(slug=slug, is_demo=True).exists()


def is_gone(hub: Hub, now: dt.datetime | None = None) -> bool:
    """Whether ``hub`` ended: cancelled, expired or purged, or a demo whose time is up (before the reaper runs)."""
    if hub.status in GONE_STATUSES:
        return True
    now = now or timezone.now()
    return hub.is_demo and hub.expires_at is not None and hub.expires_at <= now


#: The SaaS's photo of a business suspended for an unpaid invoice (``PUT /internal/hubs/{id}/state``, ``status``).
SUSPENDED = "suspended"


def is_suspended(hub: Hub) -> bool:
    """Whether the SaaS's last photo of ``hub`` says it is suspended for an unpaid invoice: it does not open until
    it is paid (the SaaS's BILLING-F16). In its 7 days of grace (``past_due``) it still works."""
    return isinstance(hub.state, dict) and hub.state.get("status") == SUSPENDED


def is_moving(hub: Hub) -> bool:
    """Whether ``hub`` is moving to another cluster (``control.hub.move``, ``base.tenancy.move``): closed meanwhile."""
    return hub.moving_to_id is not None


def is_preparing(hub: Hub) -> bool:
    """Whether ``hub`` is not ready yet (requested, being prepared, or its preparation failed and is retried)."""
    return hub.status in PREPARING_STATUSES


#: The statuses of a hub whose own database was dropped (a demo that ended).
DROPPED_STATUSES = (Hub.Status.PURGED, Hub.Status.DROPPING)


def database_is_made(hub: Hub) -> bool:
    """Whether ``hub``'s data can be entered: it shares control's (phase 1), or its own database was made (it is ready,
    or was once: ``ready_at``) and has not been dropped. A business cancelled or failed before it was ever ready has no
    database: what reaches it waits on its row for the day it is made. :func:`own_database_made` is the same, as a
    query."""
    if not hub.db_name:
        return True
    if hub.status in DROPPED_STATUSES:
        return False
    return hub.status == Hub.Status.READY or hub.ready_at is not None


def own_database_made() -> Q:
    """The rows with a database of their own that :func:`database_is_made` says was made (``migrate_hubs``'s hubs)."""
    return (
        ~Q(db_name="")
        & ~Q(status__in=DROPPED_STATUSES)
        & (Q(status=Hub.Status.READY) | Q(ready_at__isnull=False))
    )


#: The codes of a host that does not serve the app (``refusal``).
HUB_GONE = "base.hub_gone"
HUB_PREPARING = "base.hub_preparing"
HUB_SUSPENDED = "base.hub_suspended"
#: A hub whose database is moving to another cluster (round 2026-10-30b of PLAN-DB, decision 3): a few minutes.
HUB_MAINTENANCE = "base.hub_maintenance"
#: A hub whose database is not its own (``base.tenancy.identity``): nothing is served from it (phase 2, S1).
HUB_UNAVAILABLE = "base.hub_unavailable"


@dataclass(frozen=True)
class Refusal:
    """What the host of a hub that does not serve the app answers: the status and the envelope's code and message."""

    status: int
    code: str
    message: str


def refusal(hub: Hub | None, *, ended: bool = True) -> Refusal | None:
    """Why the host of ``hub`` does not serve the app, or ``None`` while it does; in the active language.

    The host gate's rule (``base.middleware``), in its order: no row 404, gone 410, still being prepared 503, moving
    to another cluster 503 (maintenance), suspended for an unpaid invoice 402. An open live stream and the print socket hear it again before each run
    (``base.operations.HubContextBuilder.refresh``). ``ended=False`` leaves out that it ended (a demo's login still
    answers then)."""
    if hub is None:
        return Refusal(404, "not_found", gettext("Not found"))
    if ended and is_gone(hub):
        return Refusal(410, HUB_GONE, gettext("This hub is no longer available."))
    if is_preparing(hub):
        return Refusal(503, HUB_PREPARING, gettext("This hub is still being prepared; try again in a few seconds."))
    if is_moving(hub):
        return Refusal(503, HUB_MAINTENANCE, gettext("This hub is under maintenance for a few minutes; try again shortly."))
    if is_suspended(hub):
        return Refusal(402, HUB_SUSPENDED, gettext("This business is suspended until its unpaid invoice is paid."))
    return None


def unavailable() -> Refusal:
    """What a hub whose database is not its own answers (503): nothing of it is served; in the active language."""
    return Refusal(503, HUB_UNAVAILABLE, gettext("This hub cannot be opened right now; try again later."))


def internal_only(ctx: OperationContext) -> None:
    """Refuse anyone but the platform: the registry's operations are the SaaS's, through the signed ``/internal``."""
    if ctx.actor != "system":
        raise PermissionDenied(gettext("Only the platform may do this."), code="base.internal_only")


def hub_answer(hub: Hub) -> dict:
    """The registry's row as ``/internal/hubs/{id}`` answers it (``HubOut``)."""
    return {field: getattr(hub, field) for field in HubOut.model_fields}
