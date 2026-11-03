"""The nightly use of each business (BASE-F40, HUBS-F21/F22; PLAN-DB §13 and round 2026-10-30, proposal (j)).

Once a UTC day ended, the worker measures it (:func:`measure`, through ``base.worker``: at :data:`MEASURE_AFTER` into the
next day, 00:15, before the SaaS's ``collect_hub_usage`` asks at 01:15 and away from Aurora's backup window, 02:00–03:00)
for every hub with its own database it serves (ready, or a business that left and keeps it), demos aside:

- ``db_bytes``: ``pg_database_size`` of its database, read in the server's catalog through the migrator's maintenance
  connection of its cluster (``base.tenancy.ops.connect_ops``, the database ``postgres``): the hub's database is never
  opened. A database that is not there leaves its hub unmeasured (logged ``base.usage.not_measured``);
- ``s3_bytes``: what its prefix holds in the file store (``base.files.used_bytes``: its files and its apps');
- ``active_users_1d`` and ``active_users_30d``: the people with activity that day, and in the 30 days that end it
  (``control.HubVisit``, noted at every login and by what they do after it, ``base.meter``: a session open for days counts
  on each of them; the visits older than the window are forgotten after).

A business without its own database (phase 1's, not cut yet) is not measured (decision 3: it never gets control's
size) and is logged once a night as ``base.usage_shared_database``. Each hub's figures replace that day's (one row per
hub and day, ``control.HubUsageDaily``) and its live queries hear it; the night also forgets the rows of the copies of the hubs' data
past their 90 days (``base.tenancy.dumps.RETENTION``), which the bucket no longer keeps (``base.hub.usage_measured``). The night itself is a
``control.UsageRun``: the first worker that claims it measures it, a run left unfinished for :data:`RUN_TAKEOVER` is taken
over, and a finished one is never measured again. ``GET /internal/usage`` (``base.internal``, ``base.usage.list``)
serves a finished night by pages of :data:`PAGE_SIZE`; before that, the day is not ready. Each row of it also says what
the serving tasks counted that day (``control.HubActivityDaily``, ``base.meter``), or null when they counted nothing.
"""

import datetime as dt
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable

import psycopg
from django.core.files.storage import storages
from django.utils import timezone

from base import files, services
from base.tenancy import dumps, names, ops
from base.tenancy.connections import control_name

logger = logging.getLogger(__name__)

#: How far into the next UTC day the night is measured.
MEASURE_AFTER = dt.timedelta(minutes=15)
#: A night a worker started and never finished is taken over after this.
RUN_TAKEOVER = dt.timedelta(hours=1)
#: The days a person's visit counts for: the day measured and the 29 before it.
WINDOW_DAYS = 30
#: The rows of one page of ``GET /internal/usage`` (the SaaS recommends 500 at most).
PAGE_SIZE = 500


def day_due(now: dt.datetime) -> dt.date:
    """The last UTC day that ended :data:`MEASURE_AFTER` before ``now``."""
    return (now.astimezone(dt.UTC) - MEASURE_AFTER).date() - dt.timedelta(days=1)


def measure(day: dt.date, *, now: dt.datetime | None = None) -> int | None:
    """Measure ``day`` for every hub with its own database; how many were measured, or ``None`` when the night is
    another worker's or done already."""
    now = now or timezone.now()
    if not services.usage_run_claim(day, now, RUN_TAKEOVER):
        return None
    measured, shared = services.hubs_to_measure()
    if shared:
        logger.info("base.usage_shared_database day=%s hubs=%d: not measured, they share control's database.", day, shared)
    sizes = database_sizes(measured)
    done = 0
    for hub in measured:
        if hub.pk not in sizes:
            logger.warning("base.usage.not_measured hub=%s day=%s: its database %s is not on its server.", hub.slug, day, hub.db_name)
            continue
        try:
            stored = files.used_bytes(storages["hub_files"], hub.pk)
        except Exception:  # the store away: this hub stays unmeasured tonight, the others go on
            logger.exception("base.usage.not_measured hub=%s day=%s: its files could not be counted.", hub.slug, day)
            continue
        on_day, in_window = services.active_people(hub.slug, day, WINDOW_DAYS)
        services.usage_recorded(
            hub.pk,
            day,
            db_bytes=sizes[hub.pk],
            s3_bytes=stored,
            active_users_1d=on_day,
            active_users_30d=in_window,
            now=now,
        )
        done += 1
    services.visits_forgotten(before=day - dt.timedelta(days=WINDOW_DAYS))
    # The copies of the hubs' data the bucket's lifecycle rule deleted (90 days): their rows go too.
    services.expired_dumps_forgotten(before=now - dumps.RETENTION)
    services.usage_run_finished(day, done, now)
    logger.info("base.usage.measured day=%s hubs=%d", day, done)
    return done


def database_sizes(hubs: Iterable) -> dict[uuid.UUID, int]:
    """``pg_database_size`` of each hub's database, by hub, from its cluster's catalog; a database that is not there is
    left out."""
    by_cluster: dict = defaultdict(list)
    for hub in hubs:
        by_cluster[hub.cluster].append(hub)
    control = control_name()
    sizes: dict[uuid.UUID, int] = {}
    for cluster, its_hubs in by_cluster.items():
        wanted = {names.validate_hub(hub.db_name, control=control): hub.pk for hub in its_hubs}
        try:
            with ops.connect_ops(cluster=cluster) as conn:
                found = conn.execute(
                    "SELECT datname, pg_database_size(datname) FROM pg_database WHERE datname = ANY(%s)", [list(wanted)]
                ).fetchall()
        except (ops.DatabaseOpsError, psycopg.Error):
            where = cluster.name if cluster is not None else "the settings' server"
            logger.exception("base.usage.not_measured cluster=%s: its catalog could not be read.", where)
            continue
        sizes.update({wanted[name]: int(size) for name, size in found})
    return sizes
