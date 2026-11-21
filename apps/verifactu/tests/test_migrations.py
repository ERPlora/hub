"""The verifactu app's migrations: declarative (no SQL, no RunPython), in step with the models, and reversible
(the app's tables come and go with its migrations, which the migrator runs per hub, on its own alias of the
business's database: a business's database of the test's own, cloned from the template as an alta clones it)."""

import io
import uuid
from pathlib import Path

import pytest

from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations import RunPython, RunSQL

from apps.verifactu.migrations import __path__ as MIGRATIONS
from apps.verifactu.tests.conftest import HUB_DB
from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs

TABLES = {
    "verifactu_config",
    "verifactu_chain",
    "verifactu_sendcontrol",
    "verifactu_record",
    "verifactu_event",
    "verifactu_aeatrecord",
    "verifactu_owncertificate",
}


def migrations():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return [
        migration
        for (app, _name), migration in loader.disk_migrations.items()
        if app == "verifactu"
    ]


def test_there_is_no_sql_and_no_data_migration():
    for migration in migrations():
        for operation in migration.operations:
            assert not isinstance(operation, (RunSQL, RunPython)), migration.name


@HUB_DB
def test_the_migrations_are_in_step_with_the_models():
    output = io.StringIO()
    call_command("makemigrations", "verifactu", "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


def test_the_first_migration_depends_on_invoicing():
    first = next(
        migration for migration in migrations() if migration.name == "0001_initial"
    )
    assert any(app == "invoice" for app, _name in first.dependencies)
    assert sorted(path.name for path in Path(MIGRATIONS[0]).glob("0*.py")) == [
        "0001_initial.py",
        "0002_own_certificate.py",
        "0003_live_paid.py",
        "0004_multiple_taxpayers_always.py",
        "0005_config_hub_id.py",
        "0006_own_certificate_issuer_check.py",
        "0007_own_certificate_aeat_proof.py",
    ]


@pytest.fixture
def migrator(hub_databases, django_db_blocker):
    """The migrator's alias of a business's database cloned for the test, dropped after it. No test case around it:
    one refuses the migrator's alias (``…__ddl``), which is not among its databases."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        alias = tenancy_connections.register_ddl_alias(name)
        try:
            yield alias
        finally:
            connections[alias].close()


def test_the_app_is_unmigrated_and_migrated_again(migrator):
    def tables():
        return {
            name
            for name in connections[migrator].introspection.table_names()
            if name.startswith("verifactu_")
        }

    def migrate(target):
        MigrationExecutor(connections[migrator]).migrate([target])

    leaf = max(migration.name for migration in migrations())
    assert tables() == TABLES
    migrate(("verifactu", None))
    assert tables() == set()
    migrate(("verifactu", leaf))
    assert tables() == TABLES
