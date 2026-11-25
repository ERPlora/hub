"""The hubs' pass of ``migrate_hubs``: whether a hub's database is behind the code, and bringing every one behind
to the code's leaf, ERPlora's own first."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from django.db import connections
from django.utils import timezone
from psycopg import errors as pg_errors

from base import registry
from base.tenancy.migrator import app_sets, schema
from control.models.hubs import Hub

logger = logging.getLogger("base.tenancy.migrator")  # logged as the migrator, whose steps these are

#: Hubs migrated at once: as many ``__ddl`` connections, within the cluster's connection budget.
HUB_WORKERS = 4
#: A hub's run cut by ``lock_timeout`` (a table held by its traffic) is tried this many times.
LOCK_TIMEOUT_ATTEMPTS = 3
#: The hubs whose database is complete: ready, or kept after leaving (a cancelled business, or one whose final copy
#: is being made, which the worker still serves; an expired demo until its purge). One being created is the worker's,
#: which runs ``ensure_schema`` itself; a failed one has no complete database; a purged one has none.
MIGRATED_STATUSES = (Hub.Status.READY, Hub.Status.CANCELLED, Hub.Status.ARCHIVING, Hub.Status.EXPIRED)


@dataclass
class HubsPass:
    """What ``migrate_hubs_behind`` did: the hubs it migrated and the ones left behind, with the reason."""

    up_to_date: int = 0
    migrated: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def is_behind(hub, code: app_sets.CodeMigrations | None = None) -> bool:
    """Whether ``hub``'s database may lack a migration of this code, as control knows it (``Hub.schema_apps``).

    Behind: marked so, or the platform or any app it has not at the code's leaf (never confirmed counts). An app it
    never turned on is not behind: its tables are made the first time it is (``base.app.enable`` → the worker's
    :func:`ensure_schema`), never here. A label or a migration the code does not have (a later code's, after a rollback:
    the database is ahead) is not behind. Opens no database.
    """
    if hub.schema_state == Hub.SchemaState.BEHIND:
        return True
    code = app_sets.code_migrations() if code is None else code
    recorded = hub.schema_apps or {}
    for label in set(app_sets.platform_apps()) | {label for label in recorded if label in code.leaves}:
        name = recorded.get(label)
        if name is None:
            return True
        if (label, name) in code.nodes and name != code.leaves[label]:
            return True
    return False


def hubs_with_a_database() -> list:
    """The hubs whose own database ``migrate_hubs`` keeps at the leaf: ERPlora's own first, then by slug. Only those
    whose database was made (``base.registry.own_database_made``): one cancelled or expired before it was ever ready
    has none, and must not stop a deploy."""
    return list(
        Hub.objects.filter(registry.own_database_made(), status__in=MIGRATED_STATUSES)
        .select_related("cluster")
        .order_by("-is_platform", "slug")
    )


def migrate_hubs_behind(*, workers: int = HUB_WORKERS) -> HubsPass:
    """``ensure_schema`` of every hub behind: ERPlora's own first, then the rest ``workers`` at a time. A hub that
    fails is marked ``behind`` (its traceback logged) and the others go on."""
    every = hubs_with_a_database()
    code = app_sets.code_migrations()
    behind = [hub for hub in every if is_behind(hub, code)]
    result = HubsPass(up_to_date=len(every) - len(behind))
    first = [hub for hub in behind if hub.is_platform]
    rest = [hub for hub in behind if not hub.is_platform]
    outcomes = [(hub, _migrate_hub(hub)) for hub in first]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="migrate_hubs") as pool:
        outcomes += zip(rest, pool.map(_migrate_hub_in_thread, rest), strict=True)
    for hub, failure in outcomes:
        if failure is None:
            result.migrated.append(hub.slug)
        else:
            result.failed[hub.slug] = failure
    return result


def _migrate_hub_in_thread(hub) -> str | None:
    try:
        return _migrate_hub(hub)
    finally:
        connections.close_all()  # this thread's own connections: control's goes back to its pool


def _migrate_hub(hub) -> str | None:
    """``ensure_schema(hub)``: the platform and the apps its database has, at the leaf (never an app it never turned
    on); tried again on a lock timeout; ``None`` if done, else why it was left behind."""
    attempt = 1
    while True:
        try:
            schema.ensure_schema(hub)
            return None
        except Exception as error:
            if _is_lock_timeout(error) and attempt < LOCK_TIMEOUT_ATTEMPTS:
                logger.warning("migrate_hubs: %s hit a lock timeout (attempt %d), trying again.", hub.slug, attempt)
                attempt += 1
                continue
            logger.exception("migrate_hubs: the hub %s (%s) was left behind.", hub.slug, hub.db_name)
            _mark_behind(hub)
            return f"{type(error).__name__}: {error}"


def _mark_behind(hub) -> None:
    try:
        Hub.objects.filter(pk=hub.pk).update(schema_state=Hub.SchemaState.BEHIND, updated_at=timezone.now())
    except Exception:
        logger.exception("migrate_hubs: the hub %s could not be marked behind in control.", hub.slug)


def _is_lock_timeout(error: BaseException | None) -> bool:
    while error is not None:
        if isinstance(error, pg_errors.LockNotAvailable):
            return True
        error = error.__cause__
    return False
