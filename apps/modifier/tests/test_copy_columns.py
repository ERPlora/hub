"""The option's fields a separate copy of the business may predate: read only when the copy's table holds them, so a
copy made before them still gives its options back, without them."""

from django.apps import apps
from django.db import connections

from apps.inventory.tests.test_recovery import direct
from apps.modifier.queries import copy_columns
from base.tenancy.context import current_alias
from base.tenancy.tests.test_recovery import fields_held_since

from .conftest import HUB_DB


@HUB_DB
def test_a_copy_made_since_options_have_allergens_holds_them():
    assert copy_columns.later_option_fields(direct()) == ("allergens",)


@HUB_DB
def test_a_copy_made_before_options_had_allergens_holds_none_of_the_later_fields():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("ALTER TABLE modifier_modifieroption DROP COLUMN allergens")

    assert copy_columns.later_option_fields(direct()) == ()


def test_each_later_field_came_after_the_migration_the_options_recovery_reads_since():
    groups, options, _categories, _links = apps.get_app_config("modifier").recoverable_from_copy()
    later = set(copy_columns.LATER_OPTION_FIELDS)

    # One the declared migration already holds is no later field: it is read with the rest, or the copy is refused.
    for recoverable in (groups, options):
        assert not later & fields_held_since("modifier", "modifieroption", recoverable.reads_since)
    assert later <= fields_held_since("modifier", "modifieroption", "0002_option_allergens")
