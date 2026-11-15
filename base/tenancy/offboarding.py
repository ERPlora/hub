"""A business that left, once its 90 days are over.

The worker's data pass (``base.worker._data``), under the row's lease, takes the business from ``cancelled`` through

1. ``archiving``: its final copy (``base.tenancy.dumps``, ``offboarding``); it can still come back (``base.hub.restore``);
2. ``dropping``: ``DROP DATABASE … WITH (FORCE)``, that database only (``base.tenancy.ops``), outside any transaction;
   from here it never comes back (``hub_purged``);
   then its files, that business's prefix in the store and no other (``base.files.delete_hub_files``);
3. ``purged``: ``base.hub.purge``, in one transaction of control, leaves the row as a tombstone.

**A business with fiscal documents is not dropped.** Its fiscal records and invoices must be archived for 6 years
(Código de Comercio, art. 30) before the drop, and that archive does not exist yet: every app that keeps such documents
answers ``fiscal_documents_kept()`` on its ``LiveAppConfig``, and with any of them (asked before the copy and again after
it: the worker still serves the business meanwhile) the business stays ``cancelled`` with its database, its row saying
why (``fiscal_archive_missing: <apps>``), and is looked at again the next day. An app that cannot be read keeps the
database too: only an app without tables there has nothing to say.

Each step is safe to run again: a copy kept is not made twice, a database or a file already gone is no failure. Whatever
fails leaves it in its status with ``attempts``, ``last_error`` and ``next_attempt_at`` (1 min, 5 min, 15 min, then every
hour): before the drop with nothing dropped, after it still ``dropping``, never ``purged``, until its files are gone too;
a worker that stops leaves it for the next one.

Control is written through ``base.services`` only (its doors to the ORM); the database is reached through ``use_hub``,
copied through ``base.tenancy.dumps`` and dropped through ``base.tenancy.ops``.
"""

import datetime as dt
import logging
from collections.abc import Callable

from django.core.files.storage import storages
from django.db.utils import ProgrammingError
from django.utils import timezone
from live.context import system_context
from live.meta import all_live_app_configs
from psycopg import errors

from base import files, registry, services
from base.schemas import HubGetIn
from base.tenancy import connections as tenancy_connections
from base.tenancy import dumps, names, ops, provision
from base.tenancy.context import AppNotCreated, use_hub
from control.models import Hub, HubDump

logger = logging.getLogger(__name__)


def fiscal_documents_kept(hub: Hub) -> list[str]:
    """The apps with fiscal documents in ``hub``'s database, by name, asked to every app that keeps them whether it is
    on or not (an app turned off keeps what it wrote). An app whose tables the database lacks has none; any other
    failure is raised: what cannot be read keeps the database."""
    kept = []
    with use_hub(hub):
        for config in all_live_app_configs():
            ask = getattr(config, "fiscal_documents_kept", None)
            if ask is None:
                continue
            try:
                if ask():
                    kept.append(config.label)
            except AppNotCreated:
                continue
            except ProgrammingError as error:
                if not isinstance(error.__cause__, errors.UndefinedTable):
                    raise
    return sorted(kept)


def _own_database(hub: Hub) -> None:
    """``InvalidDatabaseName`` unless ``hub`` names its own database: a row that names any other is never dropped."""
    own = names.hub_db_name(tenancy_connections.control_name(), hub.id)
    if hub.db_name != own:
        raise names.InvalidDatabaseName(
            f"{hub.db_name!r} is not the business {hub.slug}'s own database ({own!r}): nothing is dropped."
        )


def _held(hub: Hub, now: dt.datetime) -> bool:
    """Whether ``hub`` keeps fiscal documents, noted on its row if it does."""
    kept = fiscal_documents_kept(hub)
    if kept:
        services.offboarding_held(hub.pk, now, kept)
        logger.info("base.tenancy.offboarding.held hub=%s apps=%s: its database stays.", hub.slug, ",".join(kept))
    return bool(kept)


def _retire(hub: Hub, now: dt.datetime, cancelled: Callable[[], bool] | None) -> None:
    if hub.db_name:
        _own_database(hub)
    if hub.status != Hub.Status.DROPPING and hub.db_name and registry.database_is_made(hub):
        if _held(hub, now):
            return
        hub = services.offboarding_archiving(hub.pk, now, provision.LEASE)
        if hub is None:
            return
        if not services.final_copy_kept(hub):
            dumps.dump_hub(
                hub,
                kind=HubDump.Kind.OFFBOARDING,
                heartbeat=lambda: services.renew_lease(hub.pk, provision.LEASE),
                cancelled=cancelled,
            )
        if _held(hub, now):
            return
    dropping = services.offboarding_dropping(hub.pk, now, provision.LEASE)
    if dropping is None:
        return
    # Its database first, then its files, outside any transaction of control; its row after, in base.hub.purge's own.
    if dropping.db_name:
        tenancy_connections.close_hub_aliases(dropping)
        ops.drop_database(dropping.db_name, cluster=dropping.cluster)
    files.delete_hub_files(storages["hub_files"], dropping.pk)
    services.hub_purge(system_context(registry.REGISTRY_SCOPE), HubGetIn(id=dropping.pk))
    logger.info("base.tenancy.offboarding.purged hub=%s database=%s", dropping.slug, dropping.db_name or "-")


def retire(hub_id, now: dt.datetime, cancelled: Callable[[], bool] | None = None) -> None:
    """Take the business ``hub_id`` past its 90 days as far as it goes, its lease held: nothing before its next attempt.

    What fails is noted on it and tried again at its next attempt, never raised. A worker that stops
    (``dumps.DumpStopped``) leaves it due; a lease lost leaves it to its new holder."""
    hub = services.registry_row(hub_id)
    if hub is None or not services.past_retention(hub, now):
        return
    if hub.next_attempt_at is not None and hub.next_attempt_at > now:
        return
    try:
        _retire(hub, now, cancelled)
    except dumps.DumpStopped:
        raise
    except services.ProvisioningStopped as stopped:
        logger.info("base.tenancy.offboarding.stopped hub=%s: %s", hub.slug, stopped)
    except dumps.DumpError as failed:
        _failed(hub, failed.code, failed)
    except ops.DatabaseOpsError as refused:
        _failed(hub, "drop_failed", refused)
    except files.HubFilesNotDeleted as stayed:
        _failed(hub, "files_purge_failed", stayed)
    except names.InvalidDatabaseName as invalid:
        _failed(hub, "invalid_database_name", invalid)
    except Exception as error:
        logger.exception("base.tenancy.offboarding.failed hub=%s: an unexpected error; it is tried again.", hub.slug)
        _failed(hub, "unexpected", f"{type(error).__name__}: {error}")


def _failed(hub: Hub, code: str, why) -> None:
    logger.warning("base.tenancy.offboarding.failed hub=%s: %s: %s", hub.slug, code, why)
    services.offboarding_copy_failed(hub.pk, timezone.now(), f"{code}: {why}")
