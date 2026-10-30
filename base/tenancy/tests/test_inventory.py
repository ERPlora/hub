"""Inventory of the databases (PLAN-DB §14.1; plan 2026-10-22-fase-2-tenencia §2.1 and §4, step 2).

Every model the Hub installs, and every model its migrations ever created, belongs to one database class, from an
explicit list: ``control`` (the registry, Django's admin, auth, contenttypes and sessions, and phase 1's
``Membership`` and ``SessionOwner``), ``hub`` (``base``, ``live`` and every module of ``apps/``), ``contextual`` (the outbox and its
deliveries: in the database of the context, control's for the registry's events) or ``shared`` (the SaaS's schema).
A model nobody classified fails here and in the router, never lands anywhere by default. Own models have a UUIDv7
key. Once migrated, each database holds exactly its classes' tables and ``django_migrations``: control's, its own and
the outbox (plus phase 1's hubs' until S5, ``SHARED_MODE_EXTRA``); a hub's, those of its apps.
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
#: with its reason. S5 retires the shared database with the ``db_name=""`` branch and empties this: from then on a hub's
#: table left in control's fails the equality below.
SHARED_MODE_EXTRA: dict[str, str] = {
    inventory.HUB: (
        "phase 1's hubs (db_name='') keep base, live and every module in control's database until S5 (plan "
        "2026-10-22-fase-2-tenencia, decision 1); retired with S5."
    ),
}
#: Django's own bookkeeping, in every database it migrates.
MIGRATIONS_TABLE = "django_migrations"


def tables_of(*classes: str) -> set[str]:
    """The tables of every installed model (the auto-created ones too) whose database class is in ``classes``."""
    return {
        model._meta.db_table
        for model in _installed()
        if model._meta.managed and inventory.classify(model) in classes
    }


def test_shared_mode_extra_names_known_classes_with_their_reason():
    for database_class, reason in SHARED_MODE_EXTRA.items():
        assert database_class in inventory.CLASSES - {inventory.CONTROL}, database_class
        assert "S5" in reason, database_class


@pytest.mark.django_db
def test_controls_database_holds_exactly_controls_tables_and_phase_1s_hubs():
    from django.db import connection

    from base.tenancy.tests import hubs

    found = hubs.table_names(connection.settings_dict["NAME"])

    # The outbox is contextual: the registry's own events (base.hub.*, the demos) stay in control's after S5 too.
    expected = tables_of(inventory.CONTROL, inventory.CONTEXTUAL, *SHARED_MODE_EXTRA) | {MIGRATIONS_TABLE}
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
