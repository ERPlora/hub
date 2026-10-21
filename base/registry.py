"""What the Hub reads of its registry of hubs (``base.Hub``) outside an operation (plan 2026-10-17, §1.2).

The host gate (``base.middleware.HubHostRequiredMiddleware``) runs before any operation, so it reads the row of the
Host's slug here: no row is 404, a hub that is gone 410, one still being prepared 503. The apps ask through
``base.operations.is_demo_hub``, never here. Reads only, one indexed lookup by slug each; no cache in phase 1 (a
cache would delay the 410 of an expired demo). The writes are the operations of ``base.services``.
"""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import PermissionDenied

from base.models import Hub
from base.schemas import HubOut

#: The scope of the registry's operations (``base.hub.*``): the platform's, never a hub's.
REGISTRY_SCOPE = Scope("platform", "registry")

#: The statuses of a hub that ended: its host answers 410.
GONE_STATUSES = frozenset({Hub.Status.CANCELLED, Hub.Status.EXPIRED, Hub.Status.PURGED})
#: The statuses of a hub still being prepared: its host answers 503 and asks to try again.
PREPARING_STATUSES = frozenset({Hub.Status.REQUESTED, Hub.Status.FAILED})


def hub_by_slug(slug: str) -> Hub | None:
    """The registry's row of ``slug``, or ``None``."""
    return Hub.objects.filter(slug=slug).first()


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


def is_preparing(hub: Hub) -> bool:
    """Whether ``hub`` is not ready yet (requested, or its preparation failed and is retried)."""
    return hub.status in PREPARING_STATUSES


def internal_only(ctx: OperationContext) -> None:
    """Refuse anyone but the platform: the registry's operations are the SaaS's, through the signed ``/internal``."""
    if ctx.actor != "system":
        raise PermissionDenied(gettext("Only the platform may do this."), code="base.internal_only")


def hub_answer(hub: Hub) -> dict:
    """The registry's row as ``/internal/hubs/{id}`` answers it (``HubOut``)."""
    return {field: getattr(hub, field) for field in HubOut.model_fields}
