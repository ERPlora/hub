"""The tax categories: ``tax.category.list`` and ``tax.category.get``.

The lists are those of the current product's SQL batteries.
"""

from decimal import Decimal

import pytest
from live.errors import NotFound

from apps.tax.models import TaxCategory
from apps.tax.schemas import CategoryGetIn

from .conftest import HUB_DB, categories, category, rule, run

pytestmark = HUB_DB


# tax.category.list (TAX-F01)


def test_empty_category_list(no_seed):
    assert categories().model_dump() == {
        "rows": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_the_seeded_categories_with_their_rate_in_spain():
    page = categories(language="es")
    rows = {row.key: row for row in page.rows}
    assert [row.key for row in page.rows] == sorted(rows)  # ordered by key
    assert page.total == 11
    food, health = rows["restaurant.food"], rows["service.health"]
    assert (food.display_name, food.name, food.is_system) == (
        "Restauración — comida",
        "Restaurant — food",
        True,
    )
    assert (food.rate_pct, food.operation_class) == (Decimal("10.00"), "subject")
    assert (health.rate_pct, health.operation_class) == (Decimal("0.00"), "exempt")
    assert health.display_description.startswith("Asistencia prestada")


def test_the_rate_column_follows_the_country_and_the_region(no_seed):
    generic, food = category("product.generic"), category("restaurant.food")
    root = rule(generic, "21")
    rule(generic, "5.2", parent=root, tax_type="surcharge")
    rule(generic, "7", region="ES-CN", tax_type="igic")
    rule(food, "10")
    rates = lambda **where: {row.key: row.rate_pct for row in categories(**where).rows}  # noqa: E731
    assert rates() == {
        "product.generic": Decimal("26.20"),
        "restaurant.food": Decimal("10.00"),
    }
    # The Canary Islands never take the national VAT: a category without its IGIC has no rate there.
    assert rates(region_code="ES-CN") == {
        "product.generic": Decimal("7.00"),
        "restaurant.food": None,
    }
    assert rates(country_code="PT") == {
        "product.generic": None,
        "restaurant.food": None,
    }


def test_the_search_finds_the_stored_and_the_translated_texts(no_seed):
    category("restaurant.food", "Restaurant — food", system=True)
    category("service.health", "Service — healthcare (VAT exempt)", system=True)
    keys = lambda language, search: [  # noqa: E731
        r.key for r in categories(language=language, search=search).rows
    ]
    assert keys("es", "COMIDA") == ["restaurant.food"]  # the translated name, any case
    assert keys("es", "food") == ["restaurant.food"]  # the key (and the stored name)
    assert keys("es", "asistencia") == ["service.health"]  # the translated description
    assert keys("es", "healthcare") == ["service.health"]  # the stored name, as the current search
    assert keys("es", "nada") == []


def test_the_column_filters_read_what_the_column_shows(no_seed):
    # The description column shows the translated text; its filter reads that text.
    category("service.health", "Service — healthcare (VAT exempt)", system=True, description="Assistance by medics")
    category("product.books", "Libros", description="Solo papel")
    keys = lambda **where: [r.key for r in categories(language="es", **where).rows]  # noqa: E731
    assert keys(display_description="asistencia prestada") == ["service.health"]
    assert keys(display_description="Assistance") == []  # the stored English is not what is shown
    assert keys(display_description="papel") == ["product.books"]  # an own category, by its own text
    assert keys(display_name="sanitario") == ["service.health"]
    assert keys(name="healthcare") == ["service.health"]
    assert keys(key="books") == ["product.books"]
    assert keys() == ["product.books", "service.health"]  # no filter, no condition


def test_categories_sort_by_any_column_of_the_screen(no_seed):
    category("product.a", "Zeta")
    category("product.b", "Alfa")
    category("product.c", "Media", system=True)
    keys = lambda **order: [r.key for r in categories(**order).rows]  # noqa: E731
    assert keys() == ["product.a", "product.b", "product.c"]
    assert keys(sort="key", dir="desc") == ["product.c", "product.b", "product.a"]
    assert keys(sort="display_name") == ["product.b", "product.c", "product.a"]
    assert keys(sort="is_system", dir="desc")[0] == "product.c"


def test_only_active_categories_are_listed_and_the_row_says_it(no_seed):
    category("product.a")
    TaxCategory.objects.create(key="product.old", name="Old", is_active=False)
    page = categories()
    assert [(r.key, r.is_active) for r in page.rows] == [("product.a", True)]
    assert page.total == 1


def test_an_own_category_is_found_by_its_own_text(no_seed):
    category("product.books", "Libros y revistas", description="Solo papel")
    category("restaurant.food", "Restaurant — food", system=True)
    assert [r.key for r in categories(language="es", search="revistas").rows] == [
        "product.books"
    ]
    assert [r.key for r in categories(language="es", search="papel").rows] == [
        "product.books"
    ]
    assert [r.key for r in categories(is_system=False).rows] == ["product.books"]
    assert [r.key for r in categories(is_system=True).rows] == ["restaurant.food"]


def test_category_pages_are_stable(no_seed):
    for n in range(5):
        category(f"product.p{n}")
    pages = [categories(limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [row.key for page in pages for row in page.rows] == [
        f"product.p{n}" for n in range(5)
    ]
    assert [(page.total, len(page.rows)) for page in pages] == [(5, 2), (5, 2), (5, 1)]


# tax.category.get


def test_get_a_category_by_its_key():
    food = run(
        "tax.category.get",
        CategoryGetIn(key="restaurant.food"),
        role="hub_employee",
        language="es",
    )
    assert (food.key, food.display_name, food.is_system) == (
        "restaurant.food",
        "Restauración — comida",
        True,
    )


def test_get_a_missing_category(no_seed):
    with pytest.raises(NotFound) as excinfo:
        run("tax.category.get", CategoryGetIn(key="product.books"))
    assert str(excinfo.value.message) == "This tax category does not exist."
