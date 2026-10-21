"""Migration 0002 of the kitchen app: the settings row, made with the app's tables, says from when the
kitchen receives the rounds Sales fires (WORKBOOK «Notas técnicas»). Planted once, reversible. Migration 0004
(the options and the menu of a dish) is expand/contract: the code of before keeps saving dishes while it runs.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry
and a schema editor whose connection is the test database.
"""

import datetime as dt
import uuid
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection
from django.utils import timezone

from apps.kitchen.models import KitchenSettings, Ticket, TicketItem

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


def test_the_code_from_before_0004_still_saves_a_dish_during_the_deploy():
    """The deploy migrates before it replaces the services, so for a while the code of before inserts dishes
    with the columns it knows (its INSERT, column by column): the new columns of 0004 need their default in
    the database, not only in Python."""
    ticket = Ticket.objects.create(
        number="20261014-0007", day=dt.date(2026, 10, 14), sequence=7, received_at=timezone.now()
    )
    dish = uuid.uuid7()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO kitchen_ticketitem (id, ticket_id, sale_line_id, position, product_id, category_id, "
            "name, quantity, unit, notes, station_id, station_name, destination, printer_usage, printer_name, "
            "status, void_reason, ready_at, total) "
            "VALUES (%s, %s, %s, 1, NULL, NULL, 'Burger', 1, 'ud', '', NULL, '', 'both', 'kitchen', '', "
            "'pending', '', NULL, 1200)",
            [dish, ticket.id, uuid.uuid7()],
        )
    item = TicketItem.objects.get(pk=dish)
    assert (item.menu_dish, item.menu_name, item.modifiers) == (0, "", [])
