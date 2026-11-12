"""What Inventory gives back from a separate copy of the business (hub#1282; BASE-F114, INVENTORY-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Inventory answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its models' names (``queries.products_in_copy``): each live product of the copy
with what its create takes, its tax category and its live categories there. Then, in the business, which of those it
lacks (``queries.products_not_in_business``), each as the business's create takes it: a product the business has live
is not lacking, and neither is one with the SKU or the EAN-13 of a live one (it was made again). Each lacking product is
created by ``inventory.product.create``, the screen's own: in the categories the business still has, with no stock
(the copy's balance is another day's; a count says today's, INVENTORY-F14) and without its image (hub#1319).

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.inventory import queries
from apps.inventory.models import Category, Product, ProductCategory, StockMovement
from apps.inventory.schemas import ProductIn
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fresh, run, run_in

TAX = "test.general"
BARCODE = "8412345678905"


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


@pytest.fixture
def general(db):
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})[0]


def product(name: str, sku: str, **fields) -> Product:
    return Product.objects.create(name=name, sku=sku, price=fields.pop("price", 100), **fields)


@pytest.mark.django_db
def test_the_copy_gives_each_live_product_with_what_its_create_takes(general):
    drinks = Category.objects.create(name="Drinks")
    gone = Category.objects.create(name="Old menu", is_deleted=True)
    coffee = product(
        "Coffee",
        "COF-1",
        ean13=BARCODE,
        description="Arabica",
        product_type=Product.Type.PHYSICAL,
        price=250,
        cost=80,
        stock=Decimal("12"),
        low_stock_threshold=Decimal("5"),
        unit="kg",
        price_quantity=Decimal("0.250"),
        pricing_unit="g",
        tax_category=general,
        track_stock=True,
        is_active=False,
        is_sold_out=True,
        image="catalog:drinks/coffee",
    )
    ProductCategory.objects.create(product=coffee, category=drinks)
    ProductCategory.objects.create(product=coffee, category=gone)
    product("Deleted", "DEL-1", is_deleted=True, is_active=False)

    [read] = queries.products_in_copy(direct())

    assert (read.pop("id"), read.pop("tax_category"), read.pop("category_ids")) == (coffee.pk, general.pk, [drinks.pk])
    assert read == {
        "name": "Coffee",
        "sku": "COF-1",
        "ean13": BARCODE,
        "description": "Arabica",
        "product_type": "physical",
        "price": 250,
        "cost": 80,
        "low_stock_threshold": Decimal("5.000"),
        "unit": "kg",
        "price_quantity": Decimal("0.250"),
        "pricing_unit": "g",
        "track_stock": True,
        "is_active": False,
    }


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE inventory_product CASCADE")

    assert queries.products_in_copy(direct()) == []


def a_product_of_the_copy(found: Product | None = None, **fields) -> dict:
    """A product as the copy gives it (``found``'s codes, or new ones), with what its create takes."""
    given = {
        "id": uuid.uuid7(),
        "name": "",
        "sku": "",
        "ean13": None,
        "description": "",
        "product_type": "physical",
        "price": 100,
        "cost": 0,
        "low_stock_threshold": Decimal("10"),
        "unit": "ud",
        "price_quantity": Decimal("1"),
        "pricing_unit": "ud",
        "track_stock": None,
        "is_active": True,
        "tax_category": None,
        "category_ids": [],
    }
    if found is not None:
        given |= {"id": found.pk, "name": found.name, "sku": found.sku, "ean13": found.ean13}
    return given | fields


@pytest.mark.django_db
def test_the_business_lacks_what_it_has_not_live_nor_made_again_with_its_sku_or_barcode():
    live = product("Tea", "TEA-1")
    deleted = product("Coffee", "COF-1", ean13=BARCODE, is_deleted=True, is_active=False)
    product("Juice", "JUI-2")
    product("Water", "WAT-2", ean13="4006381333931")
    absent = a_product_of_the_copy(name="Cake", sku="CAK-1")
    # Deleted, and made again by hand since: another product with its SKU, or with its barcode.
    same_sku = a_product_of_the_copy(name="Orange juice", sku="JUI-2")
    same_barcode = a_product_of_the_copy(name="Still water", sku="WAT-1", ean13="4006381333931")
    products = [a_product_of_the_copy(live), a_product_of_the_copy(deleted), absent, same_sku, same_barcode]

    lacking = queries.products_not_in_business(products)

    assert [one["id"] for one in lacking] == [deleted.pk, absent["id"]]


@pytest.mark.django_db
def test_a_lacking_product_is_what_the_create_takes_in_the_categories_the_business_still_has(general):
    drinks = Category.objects.create(name="Drinks")
    lost = Category.objects.create(name="Desserts", is_deleted=True)
    coffee = a_product_of_the_copy(
        name="Coffee", sku="COF-1", price=250, is_active=False, tax_category=general.pk,
        category_ids=[drinks.pk, lost.pk, uuid.uuid7()],
    )

    [lacking] = queries.products_not_in_business([coffee])

    assert lacking["id"] == coffee["id"]
    payload = ProductIn.model_validate({key: value for key, value in lacking.items() if key != "id"})
    assert (payload.tax_category_key, payload.category_ids, payload.is_active) == (TAX, [drinks.pk], False)
    assert (payload.initial_stock, payload.price) == (Decimal("0"), 250)


@pytest.mark.django_db
def test_a_lacking_product_without_a_tax_category_names_none_and_its_create_says_so():
    [lacking] = queries.products_not_in_business([a_product_of_the_copy(name="Cake", sku="CAK-1", price=300)])

    assert "tax_category_key" not in lacking
    with pytest.raises(ValueError, match="tax_category_key"):
        ProductIn.model_validate({key: value for key, value in lacking.items() if key != "id"})


def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("inventory").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create) == (
        queries.products_in_copy,
        queries.products_not_in_business,
        "inventory.product.create",
    )
    assert str(declared.label) == "Products"
    assert declared.reads_since == "0001_initial"


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


def a_tax_key(hub) -> str:
    with use_hub(hub):
        return TaxCategory.objects.filter(is_active=True).order_by("key").values_list("key", flat=True).first()


def live_products(hub) -> list[tuple]:
    """The business's live products: name, SKU, whether active, stock and its categories' names, by name."""
    with use_hub(hub):
        return [
            (one.name, one.sku, one.is_active, one.stock, sorted(one.categories.filter(is_deleted=False).values_list(
                "name", flat=True)))
            for one in Product.objects.filter(is_deleted=False).order_by("name")
        ]


def created_events(hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="inventory.product.created").count()


@pytest.mark.usefixtures("no_test_fallback")
class TestProductsComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with a category and three products made by their screen's operations, and their ids."""
        hub, _ = recoveries.business(every_app_on)
        tax = a_tax_key(hub)
        drinks = run_in(hub, "inventory.category.create", name="Drinks").id
        desserts = run_in(hub, "inventory.category.create", name="Desserts").id
        made = {
            "coffee": run_in(hub, "inventory.product.create", name="Coffee", sku="COF-1", price=250,
                             tax_category_key=tax, category_ids=[drinks], initial_stock=Decimal("12")),
            "tea": run_in(hub, "inventory.product.create", name="Tea", sku="TEA-1", price=200, tax_category_key=tax,
                          category_ids=[drinks]),
            "cake": run_in(hub, "inventory.product.create", name="Cake", sku="CAK-1", price=400, tax_category_key=tax,
                           category_ids=[desserts]),
        }
        run_in(hub, "inventory.product.update", id=made["tea"].id, is_active=False)
        return hub, {name: one.id for name, one in made.items()}, desserts

    def test_the_products_the_business_lost_come_back_each_created_by_its_operation(self, recoveries, every_app_on):
        hub, ids, desserts = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        for name in ("coffee", "tea", "cake"):
            run_in(hub, "inventory.product.delete", id=ids[name])
        run_in(hub, "inventory.category.delete", id=desserts)
        before = created_events(hub)
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        row = fresh(row)
        assert (row.status, row.results) == (
            "done",
            [{"app": "inventory", "created": 3, "not_created": 0, "reasons": [], "refused": ""}],
        )
        # Active or not as it was, in the categories the business still has, and with no stock: a count says today's.
        assert live_products(hub) == [
            ("Cake", "CAK-1", True, Decimal("0.000"), []),
            ("Coffee", "COF-1", True, Decimal("0.000"), ["Drinks"]),
            ("Tea", "TEA-1", False, Decimal("0.000"), ["Drinks"]),
        ]
        assert created_events(hub) == before + 3
        with use_hub(hub):
            back = set(Product.objects.filter(is_deleted=False).values_list("pk", flat=True))
            assert not back & set(ids.values())
            assert not StockMovement.objects.filter(product__in=back).exists()

    def test_asked_again_nothing_is_made_twice_and_what_the_business_has_stays(self, recoveries, every_app_on):
        hub, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "inventory.product.delete", id=ids["coffee"])
        recoveries.ask(copy, "inventory")
        assert run() == 1
        before = created_events(hub)

        again = recoveries.ask(copy, "inventory")
        assert run() == 1

        assert fresh(again).results == [
            {"app": "inventory", "created": 0, "not_created": 0, "reasons": [], "refused": ""}
        ]
        assert created_events(hub) == before
        assert [one[0] for one in live_products(hub)] == ["Cake", "Coffee", "Tea"]

    def test_a_product_whose_tax_category_the_create_refuses_is_counted_with_why(self, recoveries, every_app_on):
        hub, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "inventory.product.delete", id=ids["coffee"])
        run_in(hub, "inventory.product.delete", id=ids["tea"])
        with use_hub(hub):
            # Taxes never deletes a tax category; one no longer active is one the create does not take.
            TaxCategory.objects.filter(key=a_tax_key(hub)).update(is_active=False)
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        [result] = fresh(row).results
        assert (result["created"], result["not_created"], result["refused"]) == (0, 2, "")
        assert {one["id"] for one in result["reasons"]} == {str(ids["coffee"]), str(ids["tea"])}
        assert all(one["reason"].startswith("invalid_field: ") for one in result["reasons"])
