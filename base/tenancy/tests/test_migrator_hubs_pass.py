"""Whether ``migrate_hubs`` opens a hub at all (``is_behind``), and its pass over the hubs behind."""

from base.tenancy.migrator import app_sets, hubs_pass, schema
from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import (
    committed_database,
    make_cluster,
    make_database,
    make_hub,
    new_database,
)
from base.tenancy.tests.test_migrator import PLATFORM, leaves
from control.models import Hub

__all__ = ["committed_database", "make_cluster", "make_database", "make_hub", "new_database"]


def test_a_hub_is_behind_when_an_app_it_has_is_not_at_the_codes_leaf():
    leaf = leaves()
    # A hub with its own database has every portable app: current is all of them.
    current = {label: leaf[label] for label in (*PLATFORM, *app_sets.portable_apps())}

    assert not hubs_pass.is_behind(Hub(schema_apps=current))
    assert hubs_pass.is_behind(Hub(schema_apps={}))  # never confirmed
    assert hubs_pass.is_behind(Hub(schema_apps={**current, "base": "0001_initial"}))
    assert hubs_pass.is_behind(Hub(schema_apps={**current, "tax": "0001_initial"}))  # an older one of the code
    assert hubs_pass.is_behind(Hub(schema_apps=current, schema_state=Hub.SchemaState.BEHIND))
    assert not hubs_pass.is_behind(Hub(schema_apps={**current, "gone": "0009_later"}))  # a rollback's unknown label
    # A later code's migration (after a rollback): the database is ahead, not behind.
    assert not hubs_pass.is_behind(Hub(schema_apps={**current, "base": "0099_from_a_later_code"}))


def test_a_hub_without_an_app_it_never_turned_on_is_not_behind():
    """An app's tables are made the first time its hub turns it on (``base.app.enable`` → the worker's
    ``ensure_schema``), never by ``migrate_hubs``: a hub with its own database that lacks one is up to date."""
    leaf = leaves()
    every = {label: leaf[label] for label in (*PLATFORM, *app_sets.portable_apps())}
    without_tax = {label: name for label, name in every.items() if label != "tax"}
    platform_only = {label: leaf[label] for label in PLATFORM}

    assert not hubs_pass.is_behind(Hub(db_name="hub_x", schema_apps=every))
    assert not hubs_pass.is_behind(Hub(db_name="hub_x", schema_apps=without_tax))
    assert not hubs_pass.is_behind(Hub(db_name="hub_x", schema_apps=platform_only))


def test_migrate_hubs_brings_what_a_hub_has_to_the_leaf_and_never_makes_an_app_it_never_turned_on(
    new_database, make_hub
):
    hub = make_hub(new_database)
    tax = leaves()["tax"]
    schema.ensure_schema(hub, add=["tax"])  # what it turned on
    hub.refresh_from_db()
    Hub.objects.filter(pk=hub.pk).update(schema_state=Hub.SchemaState.BEHIND)

    result = hubs_pass.migrate_hubs_behind(workers=1)

    assert hub.slug in result.migrated and result.failed == {}
    hub.refresh_from_db()
    assert hub.schema_apps["tax"] == tax
    assert "inventory" not in hub.schema_apps
    assert "inventory_product" not in hubs.table_names(new_database)
    assert not hubs_pass.is_behind(hub)
