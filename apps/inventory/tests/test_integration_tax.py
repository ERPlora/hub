"""Inventory together with the real Taxes app (its ``requires``), without doubles.

What tax seeds (migration 0002: the factory catalogue, its rules and its aliases), what tax
calculates and what tax deactivates is what inventory sees, through every door.
"""

from decimal import Decimal

import pytest
from live.errors import InvalidPayload
from live.operations import get

from apps.inventory.models import Category, Product
from apps.inventory.schemas import (
    CategoryImportIn,
    CategoryIn,
    ForSaleListIn,
    ProductImportIn,
    ProductIn,
    ProductListIn,
    ProductPatchIn,
    ProductRefIn,
)
from apps.tax.models import TaxCategory

from .conftest import ctx_for

pytestmark = pytest.mark.django_db

FOOD = "restaurant.food"


def run(name, data, role="hub_admin"):
    return get(name)(ctx_for(role), data)


@pytest.fixture
def food():
    """The factory category of restaurant food, as migration tax.0002 seeds it (10 % in Spain)."""
    return TaxCategory.objects.get(key=FOOD)


def paella():
    return run("inventory.product.create", ProductIn(name="Paella", sku="PAE", price=1500, tax_category_key=FOOD))


def test_a_product_with_a_factory_tax_category_can_be_sold_and_taxes_resolves_its_rate(food):
    created = paella()
    assert (created.needs_tax_setup, created.tax_category_id, created.tax_category_key) == (False, food.id, FOOD)

    # What the till reads to price the line, handed to the real calculation of Taxes.
    [line] = run("inventory.product.list_for_sale", ForSaleListIn()).rows
    calculate = get("tax.rate.calculate")
    tax = calculate(ctx_for(), calculate.input(amount=line.price, tax_category_key=line.tax_category_key, tax_included=True))

    assert (tax.tax_category_key, tax.tax_rate_pct, tax.total) == (FOOD, Decimal("10.00"), 1500)
    assert tax.base + tax.tax == 1500


def test_a_tax_category_that_taxes_deactivates_leaves_the_product_unsellable_and_every_door_refuses_it(food):
    created = paella()
    food.is_active = False  # there is no operation to deactivate a category yet: Taxes' own model
    food.save(update_fields=["is_active"])

    [row] = run("inventory.product.list", ProductListIn()).rows
    assert (row.id, row.needs_tax_setup) == (created.id, True)
    assert run("inventory.product.list_for_sale", ForSaleListIn()).rows[0].needs_tax_setup is True
    assert [r.id for r in run("inventory.product.list", ProductListIn(status="needs_tax_setup")).rows] == [created.id]

    doors = [
        lambda: run("inventory.product.create", ProductIn(name="Fideuà", sku="FID", price=1400, tax_category_key=FOOD)),
        lambda: run("inventory.product.update", ProductPatchIn(product="PAE", tax_category_key=FOOD)),
        lambda: run("inventory.category.create", CategoryIn(name="Rices", tax_category_key=FOOD)),
    ]
    for door in doors:
        with pytest.raises(InvalidPayload) as excinfo:
            door()
        assert list(excinfo.value.fields) == ["tax_category_key"]
    report = run(
        "inventory.product.bulk_create",
        ProductImportIn(rows=[{"line": 2, "name": "Fideuà", "sku": "FID", "price": "14", "tax_category_key": FOOD}]),
    )
    assert [(r.status, r.reason) for r in report.rows] == [("failed", f"Tax category not recognized: {FOOD}")]
    assert Product.objects.filter(is_deleted=False).count() == 1 and not Category.objects.exists()
    # Choosing a live one makes it sellable again.
    assert run("inventory.product.update", ProductPatchIn(product="PAE", tax_category_key="product.generic")).needs_tax_setup is False
    assert run("inventory.product.get", ProductRefIn(product="PAE")).tax_category_key == "product.generic"


def test_a_category_import_reads_its_fiscal_text_with_the_real_aliases_of_taxes(food):
    report = run(
        "inventory.category.bulk_create",
        CategoryImportIn(
            rows=[
                {"line": 2, "name": "Pizzas", "tax_category_key": "Pizza"},  # a factory alias
                {"line": 3, "name": "Rices", "tax_category_key": "Restaurant — food"},  # its name
                {"line": 4, "name": "Bottles", "tax_category_key": "retail.alcohol"},  # its key
                {"line": 5, "name": "Mystery", "tax_category_key": "IVA 99"},
            ]
        ),
    )

    assert [(r.key, r.status) for r in report.rows] == [
        ("Pizzas", "created"),
        ("Rices", "created"),
        ("Bottles", "created"),
        ("Mystery", "failed"),
    ]
    assert dict(Category.objects.values_list("name", "tax_category__key")) == {
        "Pizzas": FOOD,
        "Rices": FOOD,
        "Bottles": "retail.alcohol",
    }
