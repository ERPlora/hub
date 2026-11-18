"""The nightly use of each business (``base.usage``) and what a process counted of its activity (``base.meter``), kept
in control.
"""

import datetime as dt
from collections.abc import Mapping
from uuid import UUID

from django.db.models import F, PositiveIntegerField, Q, Value
from django.db.models.functions import Greatest
from live.context import Scope
from live.outbox import notify

from base import events
from base.models import Hub
from base.services.provisioning import SERVED_STATUSES, _control_transaction
from control.models import HubActivityDaily, HubUsageDaily, HubVisit, UsageRun


def usage_run_claim(day: dt.date, now: dt.datetime, takeover: dt.timedelta) -> bool:
    """Claim the measurement of ``day``: whether this worker measures it (no run yet, or one left unfinished for
    ``takeover``); a finished night is never measured again."""
    with _control_transaction():
        run = UsageRun.objects.select_for_update().filter(day=day).first()
        if run is None:
            UsageRun.objects.create(day=day, started_at=now)
            return True
        if run.finished_at is not None or run.started_at > now - takeover:
            return False
        run.started_at = now
        run.save(update_fields=["started_at"])
        return True


def usage_run_finished(day: dt.date, hubs: int, now: dt.datetime) -> None:
    with _control_transaction():
        UsageRun.objects.filter(day=day).update(finished_at=now, hubs=hubs)


def usage_ready(day: dt.date) -> bool:
    """Whether the night of ``day`` was measured to its end."""
    return UsageRun.objects.filter(day=day, finished_at__isnull=False).exists()


def hubs_to_measure() -> tuple[list[Hub], int]:
    """The hubs with their own database whose use is measured (a ready one, a business that left with its database
    finished; never a demo, nor one being made, dropped or gone), and how many hubs still share control's."""
    with_own = (
        Hub.objects.exclude(db_name="")
        .filter(Q(status=Hub.Status.READY) | Q(status__in=SERVED_STATUSES, ready_at__isnull=False))
        .filter(is_demo=False)
        .select_related("cluster")
        .order_by("id")
    )
    shared = Hub.objects.filter(db_name="", is_demo=False, status__in=SERVED_STATUSES).count()
    return list(with_own), shared


def active_people(host: str, day: dt.date, window_days: int) -> tuple[int, int]:
    """The people with activity in ``host`` on ``day``, and in the ``window_days`` that end it."""
    visits = HubVisit.objects.filter(host=host)
    on_day = visits.filter(day=day).values("saas_user_id").distinct().count()
    in_window = (
        visits.filter(day__gt=day - dt.timedelta(days=window_days), day__lte=day)
        .values("saas_user_id")
        .distinct()
        .count()
    )
    return on_day, in_window


def usage_recorded(  # noqa: PLR0913
    hub_id: UUID,
    day: dt.date,
    *,
    db_bytes: int,
    s3_bytes: int,
    active_users_1d: int,
    active_users_30d: int,
    now: dt.datetime,
) -> None:
    """Keep what ``hub_id`` used on ``day`` (measured again, its figures replace the day's); its live queries hear it
    after the COMMIT."""
    with _control_transaction():
        HubUsageDaily.objects.update_or_create(
            hub_id=hub_id,
            day=day,
            defaults={
                "db_bytes": db_bytes,
                "s3_bytes": s3_bytes,
                "active_users_1d": active_users_1d,
                "active_users_30d": max(active_users_30d, active_users_1d),
                "measured_at": now,
            },
        )
        slug = Hub.objects.filter(pk=hub_id).values_list("slug", flat=True).first()
    if slug:
        notify(Scope("host", slug), [events.HUB_USAGE_MEASURED])


def activity_recorded(hub_id: UUID, day: dt.date, *, requests: int = 0, peak: int = 0, busy: int = 0) -> bool:
    """Add what a process counted of ``hub_id`` on ``day`` (``base.meter``) to its row, made if it is the first; several
    tasks write at once, so it is added in the database, never read first. ``False``: the hub is gone, nothing to keep."""

    def add() -> int:
        return HubActivityDaily.objects.filter(hub_id=hub_id, day=day).update(
            requests=F("requests") + requests,
            peak_connections=Greatest(F("peak_connections"), Value(peak), output_field=PositiveIntegerField()),
            busy_requests=F("busy_requests") + busy,
        )

    with _control_transaction():
        if add():
            return True
        if not Hub.objects.filter(pk=hub_id).exists():
            return False
        _, created = HubActivityDaily.objects.get_or_create(
            hub_id=hub_id,
            day=day,
            defaults={"requests": requests, "peak_connections": peak, "busy_requests": busy},
        )
        if not created:  # another task made it meanwhile
            add()
    return True


def people_seen(host: str, day: dt.date, last_seen: Mapping[str, dt.datetime]) -> None:
    """Note who had activity in ``host`` on ``day`` and when last (``base.meter``): their visit of the day, made if it is
    the first. Two tasks may write out of order by up to a pass: a moment against a window of minutes, which it does not
    change, so one upsert is enough."""
    with _control_transaction():
        HubVisit.objects.bulk_create(
            [
                HubVisit(host=host, day=day, saas_user_id=person, last_seen_at=moment)
                for person, moment in last_seen.items()
            ],
            update_conflicts=True,
            unique_fields=["host", "day", "saas_user_id"],
            update_fields=["last_seen_at"],
        )


def visits_forgotten(*, before: dt.date) -> int:
    """Forget the visits older than ``before``: no window counts them any more."""
    with _control_transaction():
        forgotten, _ = HubVisit.objects.filter(day__lt=before).delete()
    return forgotten
