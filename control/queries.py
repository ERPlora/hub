"""Control's reads for the worker's metrics (hub#488; PLAN-AWS §8, PLAN-DB §6 and §8): plain reads of the registry, no
operation (no hub, no user: the worker's own measure, like ``base.services.hubs_to_serve``), on control's database
(the caller opens ``use_control``)."""

import datetime as dt
from dataclasses import dataclass

from django.db.models import Count, Min, Q
from django.db.models.functions import Coalesce

from base.registry import PREPARING_STATUSES
from control.models import Hub

#: A demo still open: being prepared or ready (``base.services.OPEN_DEMO_STATUSES``); once its time is up it ended.
_OPEN_DEMO_STATUSES = (*PREPARING_STATUSES, Hub.Status.READY)
#: A demo the reaper marked as ended and has not purged yet.
_ENDING_DEMO_STATUSES = (Hub.Status.EXPIRED, Hub.Status.DROPPING)


@dataclass(frozen=True)
class RegistryHealth:
    """What the registry says at one moment: since when the oldest hub still being prepared waits (``None``: none),
    how many hubs failed, and since when the oldest demo that ended waits to be dropped (``None``: none)."""

    oldest_preparing_since: dt.datetime | None
    failed: int
    oldest_ended_demo_since: dt.datetime | None


def registry_health(now: dt.datetime) -> RegistryHealth:
    """The registry's health at ``now``, in one query.

    A hub still being prepared (requested, creating, migrating, seeding, or failed and retried) waits since it was
    created; a demo whose time is up is not one of them but an ended demo, which waits to be dropped since its end
    (``expires_at``; one expired without it, since it last changed) until the reaper purges it, as
    ``base.services.reap_demos`` takes them.
    """
    demo_over = Q(is_demo=True, expires_at__lte=now)
    row = Hub.objects.aggregate(
        oldest_preparing_since=Min("created_at", filter=Q(status__in=PREPARING_STATUSES) & ~demo_over),
        failed=Count("pk", filter=Q(status=Hub.Status.FAILED) & ~demo_over),
        oldest_ended_demo_since=Min(
            Coalesce("expires_at", "updated_at"),
            filter=Q(is_demo=True)
            & (Q(status__in=_ENDING_DEMO_STATUSES) | Q(status__in=_OPEN_DEMO_STATUSES, expires_at__lte=now)),
        ),
    )
    return RegistryHealth(**row)
