"""The freeze's one row."""

from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.db import IntegrityError, connection, migrations, transaction

from control.models.freeze import Freeze

pytestmark = pytest.mark.django_db


class TestOneRow:
    def test_a_second_row_is_refused_by_the_database(self):
        # Control's migration made the first (a test that flushed the tables before may have taken it away).
        Freeze.objects.get_or_create()

        with pytest.raises(IntegrityError), transaction.atomic():
            Freeze.objects.create(frozen=True)

    def test_control_s_migration_makes_the_one_row_not_frozen_and_steps_back(self):
        migration = import_module("control.migrations.0010_freeze").Migration
        [seed] = [op for op in migration.operations if isinstance(op, migrations.RunPython)]
        Freeze.objects.all().delete()

        with connection.schema_editor() as editor:
            seed.code(django_apps, editor)
            seed.code(django_apps, editor)

        assert list(Freeze.objects.values_list("frozen", flat=True)) == [False]
        assert seed.reversible
