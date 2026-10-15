"""The verifactu app's migrations: declarative (no SQL, no RunPython), in step with the models, and reversible
(the app's tables come and go with its migrations, which phase 2's migrator runs per hub)."""

import io
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations import RunPython, RunSQL

from apps.verifactu.migrations import __path__ as MIGRATIONS

TABLES = {
    "verifactu_config",
    "verifactu_chain",
    "verifactu_sendcontrol",
    "verifactu_record",
    "verifactu_event",
    "verifactu_aeatrecord",
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


def test_the_migrations_are_in_step_with_the_models(db):
    output = io.StringIO()
    call_command("makemigrations", "verifactu", "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


def test_the_first_migration_depends_on_invoicing():
    first = next(
        migration for migration in migrations() if migration.name == "0001_initial"
    )
    assert any(app == "invoice" for app, _name in first.dependencies)
    assert sorted(path.name for path in Path(MIGRATIONS[0]).glob("0*.py")) == [
        "0001_initial.py"
    ]


@pytest.mark.django_db(transaction=True)
def test_the_app_is_unmigrated_and_migrated_again():
    def tables():
        return {
            name
            for name in connection.introspection.table_names()
            if name.startswith("verifactu_")
        }

    assert tables() == TABLES
    call_command("migrate", "verifactu", "zero", verbosity=0)
    assert tables() == set()
    call_command("migrate", "verifactu", verbosity=0)
    assert tables() == TABLES
