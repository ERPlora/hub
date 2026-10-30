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
   current) and noted in ``Hub.schema_apps`` (``{app: its leaf migration}``) with ``schema_state`` current;
3. ``seeding``: inside ``use_hub``, the blocks of the SaaS's photo kept on the row for the apps it has on (none at
   birth: a business is born with every app off, PLAN §33);
4. ``ready``, and the SaaS of a business hears it after the COMMIT (``base.services.report_ready``).

Every step is safe to run again: a database already there is gone on with (``42P04``), its identity is written once,
the migrator applies only what is missing. A step that fails leaves the hub ``failed`` with ``attempts``, a readable
``last_error`` (``<code>: <why>``: ``no_cluster_available``, ``template_missing``, ``clone_failed``,
``schema_failed``, ``unexpected``) and its ``next_attempt_at`` (1 min, 5 min, 15 min, then every hour), due again then:
never an exception out of the worker's pass. A hub cancelled, or a demo that ended, meanwhile stops there.

:func:`drop` ends a demo that ended: ``dropping``, its database dropped (``DROP DATABASE … WITH (FORCE)``, that one
only) and its rows purged (``base.demo.purge``). A business that leaves is not dropped here: it stays ``cancelled``
with its database (S2b dumps it and drops it after its 90 days).

Control is written through ``base.services`` only (its doors to the ORM); the databases are made through
``base.tenancy.ops`` and reached through ``base.tenancy.connections``.
"""

import datetime as dt
import logging
from collections.abc import Callable, Iterable

from django.apps import apps
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone
from live.context import system_context

from base import registry, services
from base.schemas import DemoSlugIn
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, inventory, migrator, names, ops
from base.tenancy.context import use_control, use_hub
from control.models import Hub

logger = logging.getLogger(__name__)

#: How long a hub's lease (``hub_due.lease_until``) lasts; every step renews it.
LEASE = dt.timedelta(seconds=60)
#: How many due hubs one pass of the worker takes.
DUE_BATCH = 20
#: What a seeding writes in the hub's database, inside ``use_hub``.
Seed = Callable[[Hub], None]


def hub_app_labels() -> frozenset[str]:
    """The apps whose tables live in a hub's database: ``base``, ``live`` and the modules."""
    return frozenset(
        config.label
        for config in apps.get_app_configs()
        if config.name.startswith(inventory.HUB_MODULES_PACKAGE)
        or inventory.APP_CLASSES.get(config.label) == inventory.HUB
    )


def portable_apps() -> frozenset[str]:
    """The hub apps whose tables can live in a hub's own database: those that refer to no control model, nor need
    (by their migrations) an app that does.

    Phase 1 links some modules to control's users (``settings.AUTH_USER_MODEL``: staff, attendance, task,
    whatsapp_inbox and what depends on them): their tables cannot be made in a hub's database until the hub has users
    of its own (PLAN-DB §2), so the templates and ``seed_local_hubs`` leave them out.
    """
    hub_apps = hub_app_labels()
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    needs = {
        label: {node[0] for leaf in graph.leaf_nodes() if leaf[0] == label for node in graph.forwards_plan(leaf)}
        & hub_apps
        for label in hub_apps
    }
    blocked = {
        label
        for label in hub_apps
        for model in apps.get_app_config(label).get_models(include_auto_created=True)
        if inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)
        for field in model._meta.get_fields()
        if field.is_relation
        and field.concrete
        and field.related_model is not None
        and inventory.classify(field.related_model) == inventory.CONTROL
    }
    while grown := {label for label in hub_apps - blocked if needs[label] & blocked}:
        blocked |= grown
    return frozenset(hub_apps - blocked)


def schema_leaves(labels) -> dict[str, str]:
    """``{app: its leaf migration in the code}`` for ``labels``: what ``Hub.schema_apps`` notes once they are at it."""
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    wanted = set(labels)
    return {app: name for app, name in sorted(graph.leaf_nodes()) if app in wanted}


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
    apps: Iterable[str] = (),
    seed: Seed | None = None,
    tell_saas: bool = True,
) -> bool:
    """Make ``hub``'s database now, under its lease; whether it is ready after.

    ``apps``: more apps than its template's whose tables it gets (``seed_local_hubs``: every app ``a`` and ``b`` turn
    on); ``seed``: what its seeding writes, inside its database (``use_hub``), after the photo kept. A hub already
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


def run_due(now: dt.datetime | None = None, *, limit: int = DUE_BATCH) -> int:
    """The worker's pass over ``hub_due``: take up to ``limit`` hubs due by ``now`` that nobody holds, make the
    databases still to make (a failed one once its ``next_attempt_at`` came) and drop the demos that ended; how many
    it worked on. A hub that fails is logged and given back: the others go on."""
    now = now or timezone.now()
    worked = 0
    with use_control():
        for hub_id in services.claim_due_hubs(now, limit, LEASE):
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


def _prepare(hub_id, *, apps: Iterable[str] = (), seed: Seed | None = None, tell_saas: bool = True) -> None:
    """The steps of a hub's preparation, its lease held; a failure is noted on it, a hub that left them is left."""
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
        labels = {"base", *apps} | (ops.recorded_apps(hub.db_name, cluster=hub.cluster) & hub_app_labels())
        try:
            migrator.migrate_apps(ddl, sorted(labels))
        except Exception as error:
            raise services.ProvisioningFailed("schema_failed", f"{type(error).__name__}: {error}") from error
        hub = services.provision_step(hub_id, Hub.Status.SEEDING, timezone.now(), LEASE)
        with use_hub(hub):
            services.apply_kept_photo(hub)
            if seed is not None:
                seed(hub)
        services.provision_ready(hub_id, timezone.now(), schema_leaves(labels), tell_saas=tell_saas)
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
