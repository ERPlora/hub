"""The tax categories: the list's filters and sort, the columns of its rows, and a new one."""

import pytest

from apps.tax.schemas.aliases import AliasOut
from apps.tax.schemas.categories import CategoryIn, CategoryListIn, CategoryOut, CategoryRowOut

from .schema_checks import invalid_fields


def test_category_list_filters_and_sort():
    params = CategoryListIn()
    assert params.model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "key": None,
        "name": None,
        "display_name": None,
        "display_description": None,
        "is_system": None,
        "sort": "key",
        "dir": "asc",
        # No country: the rate column is read in the business's jurisdiction (TAX-F11).
        "country_code": None,
        "region_code": None,
    }
    assert invalid_fields(CategoryListIn, country_code="ES", region_code="PT-20") == {
        "region_code"
    }
    for sort in (
        "key",
        "name",
        "display_name",
        "display_description",
        "is_system",
        "is_active",
        "id",
    ):
        assert CategoryListIn(sort=sort).sort == sort
    assert invalid_fields(CategoryListIn, sort="rate_pct") == {"sort"}


def test_the_rows_carry_the_columns_of_the_screens():
    assert list(CategoryOut.model_fields) == [
        "id", "key", "name", "description", "display_name", "display_description", "is_system", "is_active",
    ]  # fmt: skip
    assert list(CategoryRowOut.model_fields)[-2:] == ["rate_pct", "operation_class"]
    assert list(AliasOut.model_fields) == [
        "id", "alias", "tax_category_key", "tax_category_name", "source", "is_active",
    ]  # fmt: skip


def test_category_in():
    category = CategoryIn(key="product.books", name="  Books ")
    assert (category.key, category.name, category.description, category.is_system) == (
        "product.books",
        "Books",
        "",
        False,
    )
    assert invalid_fields(CategoryIn, key="product.books", name=" ") == {"name"}
    assert invalid_fields(CategoryIn, key="product.books", name="x" * 256) == {"name"}
    assert invalid_fields(
        CategoryIn, key="product.books", name="x", description="x" * 1001
    ) == {"description"}


@pytest.mark.parametrize("key", ["Product", "1x", "product-books", "x" * 81, ""])
def test_a_new_category_key_has_the_canonical_shape(key):
    assert invalid_fields(CategoryIn, key=key, name="Books") == {"key"}
