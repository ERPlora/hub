"""The aliases of the tax categories: ``tax.alias.list`` (TAX-F13), the outside texts the inventory importer reads as
a category.

The lists are those of the current product's SQL batteries.
"""

from .conftest import HUB_DB, aliases, food_and_book_aliases

pytestmark = HUB_DB


# tax.alias.list (TAX-F13)


def test_the_seeded_aliases():
    page = aliases(limit=100)
    assert page.total == 18
    assert [row.alias for row in page.rows] == sorted(row.alias for row in page.rows)
    beer = next(row for row in page.rows if row.alias == "beer")
    assert (beer.tax_category_key, beer.tax_category_name, beer.source) == (
        "restaurant.alcohol",
        "Restaurant — alcohol",
        "shipped",
    )


def test_alias_search_and_filters(no_seed):
    food_and_book_aliases()
    names = lambda **where: [row.alias for row in aliases(**where).rows]  # noqa: E731
    assert names(search="COMIDA") == ["comida casera"]
    assert names(search="books") == ["libros"]  # the category key
    assert names(tax_category_key="restaurant.food") == ["comida casera", "meal"]
    assert names(source="learned") == ["comida casera", "libros"]
