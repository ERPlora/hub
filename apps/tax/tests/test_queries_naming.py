"""How a person or an outside text names a tax category: ``tax.alias.resolve`` reads it by its key, then its name,
then an alias, and never as a similar one."""

import uuid

from apps.tax.models import TaxAlias

from .conftest import HUB_DB, category, resolved

pytestmark = HUB_DB


# tax.alias.resolve (TAX-F15): key, then name (in both languages), then alias


def test_resolve_by_key_name_or_alias():
    assert resolved(" Restaurant.Food ") == (
        "restaurant.food",
        "restaurant.food",
        "key",
    )
    assert resolved("Restaurant — food") == (
        "restaurant — food",
        "restaurant.food",
        "name",
    )
    # The translated name is recognised whatever the language of the reader (a CSV in Spanish).
    assert resolved("restauración — comida", language="en")[1:] == (
        "restaurant.food",
        "name",
    )
    assert resolved("BEER") == ("beer", "restaurant.alcohol", "alias")
    assert resolved("cerveza artesana") == ("cerveza artesana", None, None)


def test_an_own_category_is_recognised_by_its_name(no_seed):
    category("product.books", "Libros  y Revistas")
    assert resolved("libros y revistas")[1:] == ("product.books", "name")


def test_the_key_wins_over_an_alias_with_the_same_text(no_seed):
    generic, food = category("product.generic"), category("restaurant.food")
    TaxAlias.objects.create(alias="product.generic", category=food)
    assert resolved("product.generic")[1:] == (generic.key, "key")


def test_a_text_that_matches_nothing_is_never_a_similar_category(no_seed):
    category("restaurant.food", "Restaurant — food", system=True)
    assert resolved("restaurant")[1:] == (None, None)
    assert resolved(str(uuid.uuid7()))[1:] == (None, None)
