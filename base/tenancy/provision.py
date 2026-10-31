"""A hub's database made at sign-up, a demo's dropped when it ends (round 2026-10-30 of PLAN-DB, S2a; PLAN-DB §6, §8).

Every new hub and demo is born ``requested`` with its ``db_name`` (``base.services``: ``base.hub.register``,
``base.demo.create``) and due in ``hub_due``; the worker (``base.worker``, :func:`run_due`) or a command
(:func:`provision`) makes its database under that row's lease, in steps, each noted in control in a short transaction
of its own (``base.services``, «The provisioning's writes in control»):

1. ``creating``: the hub is placed on a cluster (``base.services.place_hub``: the open one with the fewest hubs under
   its ``max_hubs``; the settings' own server when there are no clusters; ``no_cluster_available`` when none has
   room) and its database is cloned from that cluster's template of its vertical (``<control>_template[_<vertical>]``,
   ``base.tenancy.ops``), private to the environment's roles, with its identity (``base_hub_identity``);
2. ``migrating``: the apps the clone has (its ``django_migrations``) and ``base`` are brought to the code's leaf through
   its migrator's alias (``base.tenancy.migrator.migrate_apps``: nothing to do when ``migrate_hubs`` kept the template
   current; the lease renewed between apps) and noted in ``Hub.schema_apps`` (``{app: its leaf migration}``) with ``schema_state`` current; until S3
   (an app's tables made when it is turned on), every portable app's tables are made too, so that turning one on only
   changes its row, as in phase 1;
3. ``seeding``: inside ``use_hub``, the SaaS's photo kept on the row (its people, and the blocks of the apps it has
   on: none at birth, a business is born with every app off, PLAN §33); a newer photo that arrives meanwhile is
   applied too before ``ready`` (:data:`SEED_ROUNDS`);
4. ``ready``, and the SaaS of a business hears it after the COMMIT (``base.services.report_ready``).

Every step is safe to run again: a database already there is gone on with (``42P04``), its identity is written once,
the migrator applies only what is missing. A step that fails leaves the hub ``failed`` with ``attempts``, a readable
``last_error`` (``<code>: <why>``: ``no_cluster_available``, ``template_missing``, ``clone_failed``,
``schema_failed``, ``photo_moving``, ``unexpected``) and its ``next_attempt_at`` (1 min, 5 min, 15 min, then every hour), due again then:
never an exception out of the worker's pass. A hub cancelled, or a demo that ended, meanwhile stops there.

:func:`drop` ends a demo that ended: ``dropping``, its database dropped (``DROP DATABASE … WITH (FORCE)``, that one
only) and its rows purged (``base.demo.purge``). A business that leaves is not dropped here: it stays ``cancelled``
with its database (S2b dumps it and drops it after its 90 days).

Control is written through ``base.services`` only (its doors to the ORM); the databases are made through
``base.tenancy.ops`` and reached through ``base.tenancy.connections``.
"""

import datetime as dt
import logging
import time
from collections.abc import Callable, Iterable

from django.utils import timezone
from live.context import system_context

from base import registry, services
from base.catalog import template_apps
from base.schemas import DemoSlugIn
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, migrator, names, ops
from base.tenancy.context import use_control, use_hub
from control.models import Hub

logger = logging.getLogger(__name__)

#: How long a hub's lease (``hub_due.lease_until``) lasts; every step renews it.
LEASE = dt.timedelta(seconds=60)
#: How many due hubs one pass of the worker takes, and for how long it goes on taking new ones: a few seconds a tick
#: (the rest waits for the next), so the next tick's relay of the shared database is not held back long.
DUE_BATCH = 20
DUE_PASS_SECONDS = 5.0
#: How many times a seeding applies a newer photo of the SaaS's that came while it ran, before it gives up for now
#: (``photo_moving``: it is tried again later): one each time a photo arrives between its read and ``ready``.
SEED_ROUNDS = 5
#: What a seeding writes in the hub's database, inside ``use_hub``.
Seed = Callable[[Hub], None]


def vertical_apps(vertical: str) -> list[str]:
    """The apps a hub of ``vertical`` is born with (``base.catalog.template_apps``); none for no vertical, or for one no
    module lists (its template's own apps are brought to the leaf all the same)."""
    if not vertical:
        return []
    try:
        return template_apps(vertical)
    except ValueError:
        return []


def template_for(hub: Hub) -> str:
    """The template ``hub`` is cloned from: its vertical's, or ``<control>_template`` without one."""
    try:
        return names.template_db_name(tenancy_connections.control_name(), hub.vertical or None)
    except names.InvalidDatabaseName as invalid:
        raise services.ProvisioningFailed("template_missing", str(invalid)) from invalid


def provision(
    hub,
    *,
    now: dt.datetime | None = None,
    apps: Iterable[str] | None = None,
    seed: Seed | None = None,
    tell_saas: bool = True,
) -> bool:
    """Make ``hub``'s database now, under its lease; whether it is ready after.

    ``apps``: more apps than its template's whose tables it gets; ``None`` (the worker's pass too, :func:`run_due`):
    every portable app's (``base.tenancy.migrator.apps_every_hub_gets``, which ``migrate_hubs`` also gives the hubs
    already made). That is transitional, until S3 makes an app's tables when it is turned on (``base.app.enable``,
    W6): meanwhile turning an app on only changes its row, as in phase 1, and a business born with every app off can
    turn any on. ``seed``: what its seeding writes, inside its database
    (``use_hub``), after the photo kept. A hub already
    ready is left as it is (``True``); one that is not being prepared (cancelled, gone) or whose lease someone else
    holds is not touched (``False``). A failure is noted on the hub (``failed``), never raised. ``tell_saas=False``:
    the SaaS does not hear it is ready (the local hubs, which are no business of the SaaS's).
    """
    now = now or timezone.now()
    with use_control():
        row = services.registry_row(hub.id)
        if row is None or (row.status != Hub.Status.READY and row.status not in registry.PREPARING_STATUSES):
            return False
        if row.status == Hub.Status.READY:
            return True
        if services.claim_hub(hub.id, now, LEASE) is None:
            return False
        try:
            _prepare(hub.id, apps=apps, seed=seed, tell_saas=tell_saas)
        finally:
            services.release_hub(hub.id, timezone.now())
        return services.registry_row(hub.id).status == Hub.Status.READY


def drop(hub, *, now: dt.datetime | None = None) -> bool:
    """Drop the demo ``hub`` that ended, under its lease, and purge it; whether this call purged it."""
    now = now or timezone.now()
    with use_control():
        if services.claim_hub(hub.id, now, LEASE) is None:
            return False
        try:
            return _drop(hub.id, now)
        finally:
            services.release_hub(hub.id, timezone.now())


def run_due(now: dt.datetime | None = None, *, limit: int = DUE_BATCH, budget: float = DUE_PASS_SECONDS) -> int:
    """The worker's pass over ``hub_due``: one hub at a time, each leased right before it is worked on (so no lease runs
    out while it waits its turn), up to ``limit`` hubs or ``budget`` seconds: make the databases still to make (a
    failed one once its ``next_attempt_at`` came; with every portable app's tables until S3: :func:`provision`) and drop
    the demos that ended (a failed drop once its wait is over);
    how many it worked on. A hub that fails is logged and given back: the others go on."""
    now = now or timezone.now()
    started = time.monotonic()
    worked = 0
    with use_control():
        for _ in range(limit):
            if time.monotonic() - started > budget:
                break
            hub_id = services.claim_next_due_hub(now, LEASE)
            if hub_id is None:
                break
            try:
                hub = services.registry_row(hub_id)
                if hub is None:
                    continue
                if hub.is_demo and registry.is_gone(hub, now):
                    worked += _drop(hub_id, now)
                elif hub.status in registry.PREPARING_STATUSES and (
                    hub.status != Hub.Status.FAILED or hub.next_attempt_at is None or hub.next_attempt_at <= now
                ):
                    _prepare(hub_id)
                    worked += 1
            except Exception:
                logger.exception("base.tenancy.provision.pass_failed hub=%s: it is given back and tried again.", hub_id)
            finally:
                services.release_hub(hub_id, timezone.now())
    return worked


def _prepare(hub_id, *, apps: Iterable[str] | None = None, seed: Seed | None = None, tell_saas: bool = True) -> None:
    """The steps of a hub's preparation, its lease held; a failure is noted on it, a hub that left them is left.
    ``apps=None``: every portable app's tables (until S3, :func:`provision`)."""
    if apps is None:
        apps = migrator.apps_every_hub_gets()
    try:
        hub = services.place_hub(hub_id)
        hub = services.provision_step(hub_id, Hub.Status.CREATING, timezone.now(), LEASE)
        template = template_for(hub)
        try:
            ops.clone_database(hub.db_name, template=template, cluster=hub.cluster)
        except ops.TemplateMissing as missing:
            raise services.ProvisioningFailed("template_missing", str(missing)) from missing
        except ops.DatabaseOpsError as refused:
            raise services.ProvisioningFailed("clone_failed", str(refused)) from refused
        ddl = tenancy_connections.register_ddl_alias(hub.db_name, cluster=hub.cluster)
        identity.write(ddl, hub.id)
        hub = services.provision_step(hub_id, Hub.Status.MIGRATING, timezone.now(), LEASE)
        try:
            # Its vertical's apps too: the template it was cloned from may still be being built (migrate_hubs). The
            # lease is renewed between apps: a long migration never lets another worker take the hub meanwhile.
            migrator.ensure_schema(
                hub,
                add=["base", *vertical_apps(hub.vertical), *apps],
                heartbeat=lambda: services.provision_step(hub_id, Hub.Status.MIGRATING, timezone.now(), LEASE),
            )
        except services.ProvisioningStopped:
            raise
        except Exception as error:
            raise services.ProvisioningFailed("schema_failed", f"{type(error).__name__}: {error}") from error
        hub = services.provision_step(hub_id, Hub.Status.SEEDING, timezone.now(), LEASE)
        with use_hub(hub):
            services.apply_kept_photo(hub)
            if seed is not None:
                seed(hub)
        for _ in range(SEED_ROUNDS):
            # Ready only with the photo it applied still the row's: one that came meanwhile was kept on the row only
            # (its database was not made yet) and the SaaS never sends it again, so it is applied now and checked again.
            if services.provision_ready(
                hub_id, timezone.now(), hub.schema_apps, tell_saas=tell_saas, seeded_version=hub.state_version
            ):
                break
            hub = services.registry_row(hub_id)
            with use_hub(hub):
                services.apply_kept_photo(hub)
        else:
            raise services.ProvisioningFailed(
                "photo_moving", f"the SaaS's photo kept changing while it was seeded ({SEED_ROUNDS} times)"
            )
        logger.info("base.tenancy.provision.ready hub=%s database=%s", hub.slug, hub.db_name)
    except services.ProvisioningStopped as stopped:
        logger.info("base.tenancy.provision.stopped hub=%s: %s", hub_id, stopped)
    except services.ProvisioningFailed as failed:
        services.provision_failed(hub_id, timezone.now(), str(failed))
        logger.warning("base.tenancy.provision.failed hub=%s: %s", hub_id, failed)
    except Exception as error:
        services.provision_failed(hub_id, timezone.now(), f"unexpected: {type(error).__name__}: {error}")
        logger.exception("base.tenancy.provision.failed hub=%s: an unexpected error; it is tried again.", hub_id)
    finally:
        # Its migrator's connection and its own, closed now: a pass over many hubs never holds one per hub.
        row = services.registry_row(hub_id)
        if row is not None and row.db_name:
            tenancy_connections.close_hub_aliases(row)


def _drop(hub_id, now: dt.datetime) -> bool:
    """Drop and purge the demo ``hub_id`` that ended, its lease held; whether it was one to drop."""
    hub = services.demo_dropping(hub_id, now, LEASE)
    if hub is None:
        return False
    # Its database first, outside any transaction of control; its rows after, in base.demo.purge's own.
    try:
        services.purge_demo_data(hub)
        services.demo_purge(system_context(registry.REGISTRY_SCOPE), DemoSlugIn(slug=hub.slug))
    except Exception as error:
        services.demo_drop_failed(hub_id, now, f"{type(error).__name__}: {error}")
        raise
    logger.info("base.tenancy.provision.dropped demo=%s database=%s", hub.slug, hub.db_name or "-")
    return True
