"""The product's fields a separate copy of the business may predate: read only when the copy's table holds them, so
a copy made before them still gives its products back, without them."""

from django.apps import apps
from django.db import connections

from apps.inventory import copy_columns
from apps.inventory.models import Product
from base.tenancy.context import current_alias
from base.tenancy.tests.test_recovery import fields_held_since

from .conftest import HUB_DB
from .test_recovery import direct


@HUB_DB
def test_a_copy_made_since_products_have_allergens_holds_them():
    assert copy_columns.later_product_fields(direct(), Product._meta.db_table) == ("allergens",)


@HUB_DB
def test_a_copy_made_before_products_had_allergens_holds_none_of_the_later_fields():
    with connections[current_alias()].cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("ALTER TABLE inventory_product DROP COLUMN allergens")

    assert copy_columns.later_product_fields(direct(), Product._meta.db_table) == ()


def test_each_later_field_came_after_the_migration_the_products_recovery_reads_since():
    _categories, products, _links = apps.get_app_config("inventory").recoverable_from_copy()
    later = set(copy_columns.LATER_PRODUCT_FIELDS)

    # One the declared migration already holds is no later field: it is read with the rest, or the copy is refused.
    assert not later & fields_held_since("inventory", "product", products.reads_since)
    assert later <= fields_held_since("inventory", "product", "0006_product_allergens")
