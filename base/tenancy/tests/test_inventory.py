"""Inventory of the databases (PLAN-DB §14.1; plan 2026-10-22-fase-2-tenencia §2.1 and §4, step 2).

Every model the Hub installs, and every model its migrations ever created, belongs to one database class, from an
explicit list: ``control`` (the registry, Django's admin, auth, contenttypes and sessions, and phase 1's
``Membership`` and ``SessionOwner``), ``hub`` (``base``, ``live`` and every module of ``apps/``), ``contextual`` (the outbox and its
deliveries: in the database of the context, control's for the registry's events) or ``shared`` (the SaaS's schema).
A model nobody classified fails here and in the router, never lands anywhere by default. Own models have a UUIDv7
key. Once migrated, each database holds exactly its classes' tables and ``django_migrations``: control's, its own and
the outbox (since S5, nothing of a hub's: ``SHARED_MODE_EXTRA`` is empty); a hub's, those of its apps. The suite's
control test database also holds the hubs' tables, for its tests written before the tenancy only
(``base/tenancy/tests/legacy.py``): what production's ``migrate`` makes is checked on a database of its own.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import migrations
from django.db.migrations.loader import MigrationLoader

from base.tenancy import inventory

#: Own models whose key is no UUIDv7, each with its reason.
KEY_EXCEPTIONS = {
    "shared.app": "round 16 (PLAN §21): its id is the app's label, the name shared by the catalog and the SaaS.",
    "control.hubdue": "keyed by its hub (PLAN-DB §8: hub_id is the key), one row per hub.",
    "base.hubidentity": "its one row is the hub's id, which the SaaS made (a UUIDv7 it does not mint).",
}
OWN_APPS = ("control", "base", "live", "shared")


def _installed():
    return apps.get_models(include_auto_created=True)


@pytest.mark.parametrize("model", _installed(), ids=lambda model: model._meta.label)
def test_every_installed_model_has_a_database_class(model):
    assert inventory.classify(model) in inventory.CLASSES


def test_the_classes_are_the_plans():
    from django.contrib.admin.models import LogEntry
    from django.contrib.auth.models import Permission, User
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.sessions.models import Session
    from live.models import OutboxEvent

    from apps.demo.models import Item
    from base.models import EventDelivery, HubIdentity, Membership, SessionOwner, TaskSchedule
    from control.models import Cluster, DemoCode, Hub, HubDue
    from shared.models import App

    expected = {
        Hub: inventory.CONTROL,
        DemoCode: inventory.CONTROL,
        HubDue: inventory.CONTROL,
        Cluster: inventory.CONTROL,
        User: inventory.CONTROL,
        Permission: inventory.CONTROL,
        ContentType: inventory.CONTROL,
        Session: inventory.CONTROL,
        LogEntry: inventory.CONTROL,
        Membership: inventory.CONTROL,
        SessionOwner: inventory.CONTROL,
        TaskSchedule: inventory.HUB,
        HubIdentity: inventory.HUB,
        Item: inventory.HUB,
        OutboxEvent: inventory.CONTEXTUAL,
        EventDelivery: inventory.CONTEXTUAL,
        App: inventory.SHARED,
    }
    assert {model: inventory.classify(model) for model in expected} == expected


def test_a_model_nobody_classified_is_refused():
    stranger = SimpleNamespace(
        _meta=SimpleNamespace(label_lower="audit.entry", app_label="audit", app_config=SimpleNamespace(name="audit"))
    )

    with pytest.raises(inventory.UnclassifiedModel, match="audit.entry"):
        inventory.classify(stranger)
    with pytest.raises(inventory.UnclassifiedModel):
        inventory.classify_label("audit", "entry")


def test_a_module_of_apps_is_a_hubs_whatever_its_name():
    newcomer = SimpleNamespace(
        _meta=SimpleNamespace(label_lower="loyalty.card", app_label="loyalty", app_config=SimpleNamespace(name="apps.loyalty"))
    )

    assert inventory.classify(newcomer) == inventory.HUB


def _created_by_migrations() -> set[tuple[str, str]]:
    """``(app_label, model_name)`` of every ``CreateModel`` of every migration the Hub loads, the moved ones too."""
    created = set()
    for migration in MigrationLoader(None, ignore_no_migrations=True).disk_migrations.values():
        operations = list(migration.operations)
        while operations:
            operation = operations.pop()
            if isinstance(operation, migrations.SeparateDatabaseAndState):
                operations += operation.state_operations + operation.database_operations
            elif isinstance(operation, migrations.CreateModel):
                created.add((migration.app_label, operation.name_lower))
    return created


def test_every_model_a_migration_ever_created_has_a_database_class():
    """``allow_migrate`` gets the historical models too (``base.hub`` before it moved to ``control``)."""
    unclassified = []
    for app_label, model_name in sorted(_created_by_migrations()):
        try:
            inventory.classify_label(app_label, model_name)
        except inventory.UnclassifiedModel:
            unclassified.append(f"{app_label}.{model_name}")

    assert unclassified == []


def test_the_registry_never_lands_in_a_hubs_database_under_its_old_label():
    assert inventory.classify_label("base", "hub") == inventory.CONTROL
    assert inventory.classify_label("base", "democode") == inventory.CONTROL


def test_every_exception_has_its_reason():
    for label, (database_class, reason) in inventory.MODEL_CLASSES.items():
        assert database_class in inventory.CLASSES, label
        assert len(reason) > 20, label


@pytest.mark.parametrize(
    "model",
    [
        model
        for model in _installed()
        if not model._meta.auto_created
        and (model._meta.app_config.name.startswith("apps.") or model._meta.app_label in OWN_APPS)
    ],
    ids=lambda model: model._meta.label,
)
def test_own_models_have_a_uuid7_key(model):
    if model._meta.label_lower in KEY_EXCEPTIONS:
        pytest.skip(KEY_EXCEPTIONS[model._meta.label_lower])
    key = model._meta.pk

    assert key.get_internal_type() == "UUIDField"
    assert key.default is uuid.uuid7


# ── After migrating: each database holds exactly its tables (PLAN-DB §14.1) ──────────────────────────────────────────

#: Database classes whose tables control's database also holds while phase 1's hubs share it (``db_name=""``), each
#: with its reason. Empty since S5 (``base.tenancy.cut``: every business has its own database): a hub's table that
#: production's ``migrate`` makes in control fails the equality below.
SHARED_MODE_EXTRA: dict[str, str] = {}
#: Django's own bookkeeping, in every database it migrates.
MIGRATIONS_TABLE = "django_migrations"


def tables_of(*classes: str) -> set[str]:
    """The tables of every installed model (the auto-created ones too) whose database class is in ``classes``."""
    return {
        model._meta.db_table
        for model in _installed()
        if model._meta.managed and inventory.classify(model) in classes
    }


def test_since_s5_control_shares_its_database_with_no_hub():
    assert SHARED_MODE_EXTRA == {}


@pytest.fixture
def production_control(django_db_blocker):
    """A control database migrated as production's is: ``manage.py migrate`` in a process of its own, with
    ``config.settings`` (its routers alone, not the tests' ``LegacyTablesRouter``), on a database of its own; dropped
    after the test."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    from django.db import connection
    from psycopg import sql

    from base.tenancy.tests import hubs

    name = f"{connection.settings_dict['NAME']}_prodctl"
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "DB_NAME": name}
        try:
            migrated = subprocess.run(
                [sys.executable, "manage.py", "migrate", "--noinput", "--verbosity", "0"],
                cwd=Path(__file__).resolve().parents[3],
                env=environment,
                capture_output=True,
                text=True,
                timeout=600,
            )
            assert migrated.returncode == 0, migrated.stderr[-3000:]
            yield hubs.table_names(name)
        finally:
            with hubs._maintenance() as conn:
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.django_db
def test_controls_database_as_production_migrates_it_holds_exactly_controls_tables(production_control):
    # The outbox is contextual: the registry's own events (base.hub.*, the demos) stay in control's after S5 too.
    expected = tables_of(inventory.CONTROL, inventory.CONTEXTUAL, *SHARED_MODE_EXTRA) | {MIGRATIONS_TABLE}

    assert production_control == expected, {
        "not a model's": sorted(production_control - expected),
        "missing": sorted(expected - production_control),
    }


@pytest.mark.django_db
def test_the_suites_control_database_holds_the_hubs_tables_too_only_for_its_tests_written_before_the_tenancy():
    from django.conf import settings
    from django.db import connection

    from base.tenancy.tests import hubs

    found = hubs.table_names(connection.settings_dict["NAME"])

    assert settings.DATABASE_ROUTERS[0] == "base.tenancy.tests.legacy.LegacyTablesRouter"
    expected = tables_of(inventory.CONTROL, inventory.CONTEXTUAL, inventory.HUB) | {MIGRATIONS_TABLE}
    assert found == expected, {"not a model's": sorted(found - expected), "missing": sorted(expected - found)}


@pytest.mark.django_db(databases=("default",))
def test_a_hubs_database_holds_exactly_its_apps_tables(hub_databases):
    from base.tenancy.tests import hubs

    expected = hubs.hub_tables(hub_databases.apps) | {MIGRATIONS_TABLE}

    for name in (hub_databases.a, hub_databases.b):
        found = hubs.table_names(name)
        assert found == expected, {name: {"not a model's": sorted(found - expected), "missing": sorted(expected - found)}}
    # Nothing of control's ever lands in a hub's.
    assert not expected & tables_of(inventory.CONTROL)
