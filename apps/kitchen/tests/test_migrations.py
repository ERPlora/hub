"""Migration 0002 of the kitchen app: the settings row, made with the app's tables, says from when the
kitchen receives the rounds Sales fires (WORKBOOK «Notas técnicas»). Planted once, reversible.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry
and a schema editor whose connection is the test database.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.kitchen.models import KitchenSettings

pytestmark = pytest.mark.django_db

migration = import_module("apps.kitchen.migrations.0002_settings_row")


def test_the_settings_row_is_made_with_the_tables_at_that_moment(clock):
    KitchenSettings.objects.all().delete()
    with connection.schema_editor() as editor:
        migration.plant_settings(global_apps, editor)
    row = KitchenSettings.objects.get()
    assert row.receiving_since == clock.now
    assert (row.warning_minutes, row.critical_minutes, row.works_from_screen) == (
        15,
        30,
        True,
    )


def test_planting_twice_keeps_the_row_it_found(clock):
    first = KitchenSettings.objects.get()
    first.warning_minutes = 5
    first.save()
    clock.advance(days=1)
    with connection.schema_editor() as editor:
        migration.plant_settings(global_apps, editor)
    row = KitchenSettings.objects.get()
    assert row.pk == first.pk and row.warning_minutes == 5


def test_the_reverse_removes_the_row():
    with connection.schema_editor() as editor:
        migration.remove_settings(global_apps, editor)
    assert not KitchenSettings.objects.exists()


def test_the_migration_runs_its_python_both_ways():
    operation = migration.Migration.operations[0]
    assert operation.code is migration.plant_settings
    assert operation.reverse_code is migration.remove_settings
