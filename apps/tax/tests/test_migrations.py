"""Migrations 0002 and 0005 of the tax app: the factory catalogue (TAX-F16), planted once, never clobbering,
reversible.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry
and a schema editor whose connection is the test database.
"""

from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.tax.models import TaxAlias, TaxCategory, TaxRule

pytestmark = pytest.mark.django_db

SPAIN_FROM = date(2012, 9, 1)
SPAIN_RATES = {
    "product.generic": ("21.00", "subject", ""),
    "service.generic": ("21.00", "subject", ""),
    # Review: drinks served to drink on the premises are a hospitality service (art. 91.Uno.2.2º
    # LIVA), 10 %; alcohol to take away or delivered is a sale of goods, 21 %.
    "restaurant.alcohol": ("10.00", "subject", ""),
    "retail.alcohol": ("21.00", "subject", ""),
    "restaurant.food": ("10.00", "subject", ""),
    "restaurant.drink": ("10.00", "subject", ""),
    "restaurant.delivery": ("10.00", "subject", ""),
    "product.reduced": ("10.00", "subject", ""),
    "product.super_reduced": ("4.00", "subject", ""),
    "service.health": ("0.00", "exempt", "E1"),
    "service.education": ("0.00", "exempt", "E1"),
}
SHIPPED_ALIASES = {
    "food": "restaurant.food",
    "prepared_food": "restaurant.food",
    "meal": "restaurant.food",
    "pizza": "restaurant.food",
    "drink": "restaurant.drink",
    "beverage": "restaurant.drink",
    "soft_drink": "restaurant.drink",
    "alcohol": "restaurant.alcohol",
    "beer": "restaurant.alcohol",
    "wine": "restaurant.alcohol",
    "takeaway_beer": "retail.alcohol",
    "takeaway_wine": "retail.alcohol",
    "delivery": "restaurant.delivery",
    "service": "service.generic",
    "product": "product.generic",
    "goods": "product.generic",
    "health": "service.health",
    "training": "service.education",
}


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _catalogue():
    return import_module("apps.tax.migrations.0002_factory_catalogue")


def plant():
    _catalogue().plant(global_apps, _SchemaEditor())


def unplant():
    _catalogue().unplant(global_apps, _SchemaEditor())


def spain_rules():
    return {
        rule.category.key: (
            str(rule.rate_pct),
            rule.operation_class,
            rule.exempt_reason,
        )
        for rule in TaxRule.objects.select_related("category")
    }


def test_the_migrated_database_has_the_catalogue():
    # The test database is built by the migrations, as a hub's is when it turns the app on.
    assert TaxCategory.objects.filter(is_system=True).count() == 11
    assert spain_rules() == SPAIN_RATES


def test_plant_on_empty_tables(no_seed):
    plant()

    categories = {cat.key: cat for cat in TaxCategory.objects.all()}
    assert set(categories) == set(SPAIN_RATES)
    assert all(cat.is_system for cat in categories.values())
    # The row keeps the English source; the reader sees it translated (models.SYSTEM_CATEGORY_LABELS).
    assert categories["restaurant.food"].name == "Restaurant — food"
    assert categories["service.health"].description == (
        "Assistance provided by medical or health professionals — art. 20.Uno.3 (ES)"
    )

    assert spain_rules() == SPAIN_RATES
    for rule in TaxRule.objects.all():
        assert (rule.country_code, rule.region_code, rule.parent_id) == ("ES", "", None)
        assert (rule.valid_from, rule.valid_to, rule.is_active, rule.tax_type) == (
            SPAIN_FROM,
            None,
            True,
            "vat",
        )
    exempt = TaxRule.objects.get(category__key="service.health")
    assert (exempt.regime_key, exempt.exempt_reason) == ("01", "E1")

    aliases = dict(TaxAlias.objects.values_list("alias", "category__key"))
    assert aliases == SHIPPED_ALIASES
    assert set(TaxAlias.objects.values_list("source", flat=True)) == {"shipped"}


def test_no_igic_ipsi_surcharge_or_other_country_is_planted(no_seed):
    # A made-up rate would be declared to the tax agency as if it were valid.
    plant()
    assert set(
        TaxRule.objects.values_list("country_code", "region_code", "tax_type")
    ) == {("ES", "", "vat")}


def test_planting_twice_duplicates_nothing(no_seed):
    plant()
    counts = (
        TaxCategory.objects.count(),
        TaxRule.objects.count(),
        TaxAlias.objects.count(),
    )
    plant()
    assert (
        (TaxCategory.objects.count(), TaxRule.objects.count(), TaxAlias.objects.count())
        == counts
        == (11, 11, 18)
    )


def test_planting_never_clobbers_what_exists(no_seed):
    food = TaxCategory.objects.create(key="restaurant.food", name="Comida de la casa")
    generic = TaxCategory.objects.create(
        key="product.generic", name="Product — generic", is_system=True
    )
    # A Spanish rule of the business for product.generic, deactivated: it is not recreated nor reactivated.
    TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("18"), is_active=False
    )
    # The business pointed "beer" at its own category.
    TaxAlias.objects.create(alias="beer", category=food)

    plant()

    food.refresh_from_db()
    assert (food.name, food.is_system) == ("Comida de la casa", False)
    generic_rules = TaxRule.objects.filter(category=generic)
    assert [(str(r.rate_pct), r.is_active) for r in generic_rules] == [("18.00", False)]
    assert TaxAlias.objects.get(alias="beer").category == food
    assert TaxCategory.objects.count() == 11 and TaxAlias.objects.count() == 18


def test_unplant_removes_the_catalogue_and_nothing_else(no_seed):
    plant()
    books = TaxCategory.objects.create(key="product.books", name="Books")
    TaxRule.objects.create(category=books, country_code="ES", rate_pct=Decimal("4"))
    TaxAlias.objects.create(alias="libros", category=books)

    unplant()

    assert list(TaxCategory.objects.values_list("key", flat=True)) == ["product.books"]
    assert list(TaxRule.objects.values_list("category__key", flat=True)) == [
        "product.books"
    ]
    assert list(TaxAlias.objects.values_list("alias", flat=True)) == ["libros"]

    plant()  # and it plants again
    assert TaxCategory.objects.count() == 12  # the 11 of the catalogue and the business's own


def test_the_alcohol_categories(no_seed):
    plant()
    served = TaxCategory.objects.get(key="restaurant.alcohol")
    to_take_away = TaxCategory.objects.get(key="retail.alcohol")
    assert served.description == "Alcoholic drinks served to drink on the premises — art. 91.Uno.2.2 (ES)"
    assert (to_take_away.name, to_take_away.is_system) == ("Retail — alcohol to take away", True)
    assert to_take_away.description == "Alcoholic drinks sold to take away or delivered — art. 90 (ES)"


# 0005: a hub that ran the first 0002 (restaurant.alcohol at 21 %, no retail.alcohol) gets the new
# category without anything it has being touched.


def _retail():
    return import_module("apps.tax.migrations.0005_retail_alcohol")


def _as_the_first_seed_left_it():
    plant()
    TaxAlias.objects.filter(category__key="retail.alcohol").delete()
    TaxRule.objects.filter(category__key="retail.alcohol").delete()
    TaxCategory.objects.filter(key="retail.alcohol").delete()
    TaxRule.objects.filter(category__key="restaurant.alcohol").update(rate_pct=Decimal("21"))


def test_0005_adds_the_take_away_alcohol_and_keeps_what_the_hub_has(no_seed):
    _as_the_first_seed_left_it()

    _retail().plant(global_apps, _SchemaEditor())

    assert spain_rules()["retail.alcohol"] == ("21.00", "subject", "")
    assert dict(TaxAlias.objects.filter(category__key="retail.alcohol").values_list("alias", "source")) == {
        "takeaway_beer": "shipped",
        "takeaway_wine": "shipped",
    }
    # The hub's rule for restaurant.alcohol is its own now: a migration never rewrites a rate.
    assert spain_rules()["restaurant.alcohol"] == ("21.00", "subject", "")


def test_0005_on_a_new_hub_changes_nothing_and_reverts_only_its_part(no_seed):
    plant()
    before = (TaxCategory.objects.count(), TaxRule.objects.count(), TaxAlias.objects.count())
    _retail().plant(global_apps, _SchemaEditor())
    assert (TaxCategory.objects.count(), TaxRule.objects.count(), TaxAlias.objects.count()) == before

    _retail().unplant(global_apps, _SchemaEditor())

    assert not TaxCategory.objects.filter(key="retail.alcohol").exists()
    assert not TaxAlias.objects.filter(alias__startswith="takeaway_").exists()
    assert (TaxCategory.objects.count(), TaxRule.objects.count(), TaxAlias.objects.count()) == (10, 10, 16)
