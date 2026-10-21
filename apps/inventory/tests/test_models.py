"""Models of the inventory app: UUIDv7 keys, live codes unique, the units register and the ledger's rules."""

import uuid
from decimal import Decimal
from fractions import Fraction

import pytest
from django.db import IntegrityError, connection, models, transaction

from apps.inventory.models import (
    UNIT_SPECS,
    Category,
    Product,
    ProductCategory,
    RefundStock,
    SaleStock,
    Settings,
    StockMovement,
    Unit,
    fits_unit,
    increment_of,
)
from apps.inventory.schemas import UnitCode

pytestmark = pytest.mark.django_db


def make(sku="CAF-1", name="Coffee", **fields):
    return Product.objects.create(name=name, sku=sku, **{"price": 150, **fields})


def rejected(constraint, action):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        action()
    assert constraint in str(excinfo.value)


# Keys and defaults


def test_keys_are_uuid7():
    product = make()
    category = Category.objects.create(name="Drinks")
    movement = StockMovement.objects.create(
        product=product, movement_type="reception", qty=1, stock_after=1
    )
    assert {
        product.pk.version,
        category.pk.version,
        movement.pk.version,
        Settings.objects.create().pk.version,
    } == {7}


def test_product_defaults():
    product = make()
    product.refresh_from_db()
    assert (
        product.product_type,
        product.cost,
        product.stock,
        product.low_stock_threshold,
    ) == (
        "physical",
        0,
        Decimal("0.000"),
        Decimal("10.000"),
    )
    assert (product.unit, product.price_quantity, product.pricing_unit) == (
        "ud",
        Decimal("1.000"),
        "ud",
    )
    assert (
        product.track_stock,
        product.is_active,
        product.is_sold_out,
        product.is_deleted,
        product.ean13,
    ) == (None, True, False, False, None)
    assert product.tax_category_id is None


def test_a_product_written_by_code_that_does_not_know_the_sold_out_mark_is_on_sale():
    """Expand/contract: while a deploy rolls, a process still on the previous code inserts products
    without the column; the database gives it its default instead of refusing the row."""
    product_id = uuid.uuid7()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO inventory_product (id, name, sku, description, product_type, price, cost, stock,"
            " low_stock_threshold, unit, price_quantity, pricing_unit, is_active, is_deleted, created_at,"
            " updated_at, created_by, updated_by) VALUES (%s, 'Old', 'OLD-1', '', 'physical', 100, 0, 0, 10,"
            " 'ud', 1, 'ud', true, false, now(), now(), '', '')",
            [product_id],
        )
    assert Product.objects.get(pk=product_id).is_sold_out is False


def test_quantities_keep_three_decimals():
    product = make(stock=Decimal("0.532"), unit="kg")
    product.refresh_from_db()
    assert product.stock == Decimal("0.532")


def test_settings_defaults_are_the_factory_ones():
    settings = Settings.objects.create()
    assert (
        settings.allow_sell_without_stock,
        settings.low_stock_threshold,
        settings.track_stock,
    ) == (False, 10, True)


def test_category_defaults():
    category = Category.objects.create(name="Drinks")
    category.refresh_from_db()
    assert (
        category.slug,
        category.description,
        category.icon,
        category.color,
        category.order,
    ) == ("", "", "ion:cube-outline", "#3880ff", 0)
    # The old module's defaults, which the till's category strip paints.
    assert (category.is_deleted, category.tax_category_id) == (False, None)


# Live codes


def test_two_live_products_cannot_share_a_sku():
    make("CAF-1")
    rejected("inventory_product_live_sku_unique", lambda: make("CAF-1", name="Other"))


def test_a_deleted_product_frees_its_sku_and_its_ean13():
    make("CAF-1", ean13="8412345678905", is_deleted=True, is_active=False)
    again = make("CAF-1", ean13="8412345678905")
    assert Product.objects.filter(sku="CAF-1").count() == 2
    assert again.is_deleted is False


def test_two_live_products_cannot_share_an_ean13():
    make("A", ean13="8412345678905")
    rejected(
        "inventory_product_live_ean13_unique", lambda: make("B", ean13="8412345678905")
    )


def test_products_without_ean13_never_collide():
    make("A")
    make("B")
    assert Product.objects.count() == 2


# Money and quantities


def test_price_and_cost_are_never_negative():
    with pytest.raises(IntegrityError), transaction.atomic():
        make(price=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        make("B", cost=-1)


def test_a_price_quantity_is_positive():
    rejected(
        "inventory_product_price_quantity_positive", lambda: make(price_quantity=0)
    )


def test_a_threshold_is_never_negative():
    rejected(
        "inventory_product_threshold_not_negative", lambda: make(low_stock_threshold=-1)
    )


# The units register (code, not a table: a business never creates units)


def test_the_eight_units_of_the_register():
    assert Unit.values == ["ud", "kg", "g", "t", "l", "ml", "min", "h"]
    assert set(UNIT_SPECS) == set(Unit.values)
    assert list(UnitCode.__args__) == Unit.values


def test_each_unit_has_its_step():
    # A loose unit does not split, the kilo and the litre step by gram and millilitre, the tonne by
    # kilo and the hour bills in quarters.
    assert {code: increment_of(code) for code in Unit.values} == {
        "ud": Decimal("1"),
        "kg": Decimal("0.001"),
        "g": Decimal("1"),
        "t": Decimal("0.001"),
        "l": Decimal("0.001"),
        "ml": Decimal("1"),
        "min": Decimal("1"),
        "h": Decimal("0.25"),
    }


def test_factors_are_exact_fractions_towards_the_reference_of_their_category():
    assert UNIT_SPECS["h"].factor == Fraction(60)
    assert UNIT_SPECS["g"].factor == Fraction(1, 1000)
    assert UNIT_SPECS["t"].factor == Fraction(1000)
    references = {
        spec.category: code for code, spec in UNIT_SPECS.items() if spec.is_reference
    }
    assert references == {"count": "ud", "mass": "kg", "volume": "l", "time": "min"}
    assert all(UNIT_SPECS[code].factor == 1 for code in references.values())


@pytest.mark.parametrize(
    ("qty", "unit", "fits"),
    [
        ("0.5", "kg", True),
        ("0.532", "kg", True),
        ("0.0005", "kg", False),
        ("1.5", "ud", False),
        ("3", "ud", True),
        ("1.25", "h", True),
        ("1.1", "h", False),
        ("-2", "ud", True),
        ("0", "g", True),
    ],
)
def test_a_quantity_fits_its_unit_only_on_its_step(qty, unit, fits):
    assert fits_unit(Decimal(qty), unit) is fits


# Categories of a product


def test_a_product_is_linked_to_a_category_once():
    product, category = make(), Category.objects.create(name="Drinks")
    ProductCategory.objects.create(product=product, category=category)
    assert list(product.categories.all()) == [category]
    rejected(
        "inventory_product_category_unique",
        lambda: ProductCategory.objects.create(product=product, category=category),
    )


# The ledger


def test_a_movement_always_changes_the_balance():
    product = make()
    rejected(
        "inventory_movement_qty_not_zero",
        lambda: StockMovement.objects.create(
            product=product, movement_type="count", qty=0, stock_after=0
        ),
    )


def test_movement_types():
    assert StockMovement.Type.values == [
        "initial",
        "reception",
        "sale",
        "void",
        "count",
        "write_off",
        "refund",
    ]


def test_a_product_with_movements_is_never_deleted_from_the_database():
    product = make()
    StockMovement.objects.create(
        product=product, movement_type="initial", qty=1, stock_after=1
    )
    with pytest.raises(models.ProtectedError):
        product.delete()


# Settings and sales


def test_there_is_one_settings_row_at_most():
    Settings.objects.create()
    rejected("inventory_settings_single_row", lambda: Settings.objects.create())


def test_a_sale_is_recorded_once():
    sale = SaleStock.objects.create(
        sale_id="0199a6c0-0000-7000-8000-000000000001", state="moved"
    )
    assert sale.pk.version == 7
    rejected(
        "inventory_sale_stock_sale_unique",
        lambda: SaleStock.objects.create(sale_id=sale.sale_id, state="voided"),
    )


def test_a_refund_is_recorded_once():
    refund = RefundStock.objects.create(
        refund_id="0199a6c0-0000-7000-8000-000000000002", sale_id="0199a6c0-0000-7000-8000-000000000001", movements=1
    )
    assert refund.pk.version == 7
    rejected(
        "inventory_refund_stock_refund_unique",
        lambda: RefundStock.objects.create(refund_id=refund.refund_id, sale_id=refund.sale_id),
    )


# The tax category (tax is a ``requires``)


def test_a_product_and_a_category_point_at_a_tax_category_that_cannot_be_deleted_under_them():
    from apps.tax.models import TaxCategory

    general = TaxCategory.objects.create(key="test.general", name="General")
    coffee = make(tax_category=general)
    Category.objects.create(name="Drinks", tax_category=general)
    assert coffee.tax_category == general
    with pytest.raises(models.ProtectedError):
        general.delete()
    # tax knows nothing about inventory: no reverse accessor on its model.
    assert not hasattr(general, "product_set")
