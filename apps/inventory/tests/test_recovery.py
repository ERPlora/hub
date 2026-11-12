"""What Inventory gives back from a separate copy of the business (BASE-F114, INVENTORY-F07, INVENTORY-F34).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Inventory answers with its own SQL over its models' names. First its categories: each one the
business lacks is created again by ``inventory.category.recover``, with the products the copy had in it that the
business still holds deleted, so they come back inside it. Then its products: each one the business still holds deleted
comes back the same by ``inventory.product.restore``, and each one it no longer holds at all is created by
``inventory.product.create`` in its categories here (the same one, or the one with its name).

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.inventory import queries
from apps.inventory.models import (
    DEFAULT_CATEGORY_COLOR,
    DEFAULT_CATEGORY_ICON,
    Category,
    Product,
    ProductCategory,
    StockMovement,
)
from apps.inventory.schemas import CategoryRecoverIn, ProductIn
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
    # A deleted product keeps its links: neither it nor what hangs from it is read.
    deleted = product("Deleted", "DEL-1", is_deleted=True, is_active=False)
    ProductCategory.objects.create(product=deleted, category=drinks)
    empty = Category.objects.create(name="Empty")

    [read] = queries.products_in_copy(direct())

    assert (read.pop("id"), read.pop("tax_category"), read.pop("category_ids")) == (coffee.pk, general.pk, [drinks.pk])
    # Every live category of the copy, by id, to tell its own from one the business made again with its name.
    assert read.pop("copy_categories") == {drinks.pk: "Drinks", empty.pk: "Empty"}
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
        "copy_categories": {},
    }
    if found is not None:
        given |= {"id": found.pk, "name": found.name, "sku": found.sku, "ean13": found.ean13}
    return given | fields


@pytest.mark.django_db
def test_the_business_lacks_only_what_it_no_longer_holds_nor_made_again_with_its_sku_or_barcode():
    live = product("Tea", "TEA-1")
    # Deleted, it is still held: it comes back the same (products_deleted_in_business), never created again.
    deleted = product("Coffee", "COF-1", ean13=BARCODE, is_deleted=True, is_active=False)
    product("Juice", "JUI-2")
    product("Water", "WAT-2", ean13="4006381333931")
    absent = a_product_of_the_copy(name="Cake", sku="CAK-1")
    # Gone, and made again by hand since: another product with its SKU, or with its barcode.
    same_sku = a_product_of_the_copy(name="Orange juice", sku="JUI-2")
    same_barcode = a_product_of_the_copy(name="Still water", sku="WAT-1", ean13="4006381333931")
    products = [a_product_of_the_copy(live), a_product_of_the_copy(deleted), absent, same_sku, same_barcode]

    lacking = queries.products_not_in_business(products)

    assert [one["id"] for one in lacking] == [absent["id"]]


@pytest.mark.django_db
def test_the_business_holds_deleted_what_comes_back_the_same_unless_its_codes_were_taken_since():
    live = product("Tea", "TEA-1")
    deleted = product("Coffee", "COF-1", ean13=BARCODE, is_deleted=True, is_active=False)
    without_barcode = product("Cake", "CAK-1", is_deleted=True, is_active=False)
    # Deleted, and made again by hand since: another live product took its SKU, or its barcode.
    taken_sku = product("Juice", "JUI-1", is_deleted=True, is_active=False)
    product("Orange juice", "JUI-1")
    taken_barcode = product("Water", "WAT-1", ean13="4006381333931", is_deleted=True, is_active=False)
    product("Still water", "WAT-2", ean13="4006381333931")
    absent = a_product_of_the_copy(name="Bread", sku="BRE-1")
    products = [
        a_product_of_the_copy(one) for one in (live, deleted, without_barcode, taken_sku, taken_barcode)
    ] + [absent]

    held = queries.products_deleted_in_business(products)

    assert [one["id"] for one in held] == [deleted.pk, without_barcode.pk]


@pytest.mark.django_db
def test_a_lacking_product_is_what_the_create_takes_in_the_categories_the_business_still_has(general):
    drinks = Category.objects.create(name="Drinks")
    lost = Category.objects.create(name="Desserts", is_deleted=True)
    gone = uuid.uuid7()
    coffee = a_product_of_the_copy(
        name="Coffee", sku="COF-1", price=250, is_active=False, tax_category=general.pk,
        category_ids=[drinks.pk, lost.pk, gone],
        copy_categories={drinks.pk: "Drinks", lost.pk: "Desserts", gone: "Old menu"},
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


def category(name: str, **fields) -> Category:
    return Category.objects.create(name=name, **fields)


def a_category_of_the_copy(found: Category | None = None, **fields) -> dict:
    """A category as the copy gives it (``categories_in_copy``): ``found``'s, or a new one with ``fields``."""
    given = {
        "id": uuid.uuid7(),
        "name": "",
        "slug": "",
        "description": "",
        "icon": DEFAULT_CATEGORY_ICON,
        "color": DEFAULT_CATEGORY_COLOR,
        "order": 0,
        "tax_category": None,
        "product_ids": [],
    }
    if found is not None:
        given |= {"id": found.pk, "name": found.name}
    return given | fields


@pytest.mark.django_db
def test_the_copy_gives_each_live_category_with_what_its_create_takes_and_the_live_products_in_it(general):
    drinks = category(
        "Drinks", slug="bar", description="Hot and cold", icon="ion:wine-outline", color="#aa3300", order=2,
        tax_category=general,
    )
    empty = category("Empty")
    gone = category("Old menu", is_deleted=True)
    coffee, tea = product("Coffee", "COF-1"), product("Tea", "TEA-1")
    deleted = product("Deleted", "DEL-1", is_deleted=True, is_active=False)
    for one in (tea, coffee, deleted):
        ProductCategory.objects.create(product=one, category=drinks)
    # The screen's delete unlinks every product of a category; a raw write may leave one.
    ProductCategory.objects.create(product=coffee, category=gone)

    read = queries.categories_in_copy(direct())

    # A deleted product, which keeps its links, is not the copy's to give back: it is never read as in one.
    assert read == [
        a_category_of_the_copy(
            drinks, slug="bar", description="Hot and cold", icon="ion:wine-outline", color="#aa3300", order=2,
            tax_category=general.pk, product_ids=[coffee.pk, tea.pk],
        ),
        a_category_of_the_copy(empty),
    ]


@pytest.mark.django_db
def test_a_copy_without_the_category_table_gives_no_category():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE inventory_category CASCADE")

    assert queries.categories_in_copy(direct()) == []


@pytest.mark.django_db
def test_a_lacking_category_comes_as_its_recover_takes_it_with_the_deleted_products_it_had(general):
    drinks = category("Drinks")
    desserts = category("Desserts", is_deleted=True)
    cake = product("Cake", "CAK-1", is_deleted=True, is_active=False)
    # Kept live by the business since: it stays as it is.
    brownie = product("Brownie", "BRO-1")
    # Deleted, and made again by hand since with its SKU: it never comes back, so it is not put back in.
    flan = product("Flan", "FLA-1", is_deleted=True, is_active=False)
    product("Flan again", "FLA-1")
    copy = [
        a_category_of_the_copy(drinks, product_ids=[brownie.pk]),
        a_category_of_the_copy(
            desserts, slug="sweet", description="After the meal", icon="ion:ice-cream-outline", color="#cc0066",
            order=3, tax_category=general.pk, product_ids=[cake.pk, brownie.pk, flan.pk, uuid.uuid7()],
        ),
        wines := a_category_of_the_copy(name="Wines"),
    ]

    lacking = queries.categories_not_in_business(copy)

    assert lacking == [
        {
            "id": desserts.pk,
            "name": "Desserts",
            "slug": "sweet",
            "description": "After the meal",
            "icon": "ion:ice-cream-outline",
            "color": "#cc0066",
            "order": 3,
            "tax_category_key": TAX,
            "product_ids": [cake.pk],
        },
        {
            "id": wines["id"],
            "name": "Wines",
            "slug": "",
            "description": "",
            "icon": DEFAULT_CATEGORY_ICON,
            "color": DEFAULT_CATEGORY_COLOR,
            "order": 0,
            "product_ids": [],
        },
    ]
    for record in lacking:
        CategoryRecoverIn.model_validate({key: value for key, value in record.items() if key != "id"})


@pytest.mark.django_db
def test_a_category_the_business_made_again_by_hand_is_never_made_twice():
    gone = category("Desserts", is_deleted=True)
    # The same name, the case and the spaces aside.
    category("  DESSERTS ")

    assert queries.categories_not_in_business([a_category_of_the_copy(gone)]) == []


@pytest.mark.django_db
def test_a_category_the_business_renamed_since_is_the_same_one_whoever_took_its_old_name():
    drinks = category("Drinks")
    copy = [a_category_of_the_copy(drinks)]
    coffee = a_product_of_the_copy(
        name="Coffee", sku="COF-1", category_ids=[drinks.pk], copy_categories={drinks.pk: "Drinks"}
    )
    # Renamed since, and its old name taken by one made after: the copy's is the renamed one, by its id before any name.
    Category.objects.filter(pk=drinks.pk).update(name="Beverages")
    category("Drinks")

    assert queries.categories_not_in_business(copy) == []
    [lacking] = queries.products_not_in_business([coffee])
    assert lacking["category_ids"] == [drinks.pk]


@pytest.mark.django_db
def test_each_one_made_again_stands_for_one_category_of_the_copy_the_oldest_first():
    kept = category("Specials")
    lost, also_lost = category("Specials", is_deleted=True), category("Specials", is_deleted=True)
    first_again = category("specials")
    copy = [a_category_of_the_copy(one) for one in (also_lost, kept, lost)]

    # The one the business kept is the copy's own, never another's made again; the one made again by hand stands for
    # the oldest lost, so the other comes back.
    assert [one["id"] for one in queries.categories_not_in_business(copy)] == [also_lost.pk]

    # Brought back: each lost one is now its own, so a product of the copy goes into each by the same pairing.
    second_again = category("SPECIALS")
    cake = a_product_of_the_copy(
        name="Cake", sku="CAK-1", category_ids=[also_lost.pk, kept.pk, lost.pk],
        copy_categories={one["id"]: one["name"] for one in copy},
    )
    [lacking] = queries.products_not_in_business([cake])
    assert lacking["category_ids"] == [second_again.pk, kept.pk, first_again.pk]


@pytest.mark.django_db
def test_a_lacking_product_goes_into_its_category_brought_back_just_before_with_its_name():
    desserts = category("Desserts", is_deleted=True)
    # What the categories' part of the same recovery created just before: a new one, the same name.
    back = category("Desserts")
    cake = a_product_of_the_copy(
        name="Cake", sku="CAK-1", category_ids=[desserts.pk], copy_categories={desserts.pk: "Desserts"}
    )

    [lacking] = queries.products_not_in_business([cake])

    assert lacking["category_ids"] == [back.pk]


@pytest.mark.django_db
def test_with_nothing_read_nothing_is_lacking():
    # The platform asks what is lacking also when the copy gave nothing.
    assert queries.categories_not_in_business([]) == []
    assert queries.products_not_in_business([]) == []


def test_the_app_declares_what_it_gives_back_its_categories_first():
    categories, products = apps.get_app_config("inventory").recoverable_from_copy()

    assert (categories.read, categories.missing, categories.create, categories.deleted, categories.restore) == (
        queries.categories_in_copy,
        queries.categories_not_in_business,
        "inventory.category.recover",
        None,
        "",
    )
    assert (products.read, products.missing, products.create, products.deleted, products.restore) == (
        queries.products_in_copy,
        queries.products_not_in_business,
        "inventory.product.create",
        queries.products_deleted_in_business,
        "inventory.product.restore",
    )
    assert (str(categories.label), str(products.label)) == ("Product categories", "Products")
    assert categories.reads_since == products.reads_since == "0001_initial"


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


def events_named(hub, name: str) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name=name).count()


def gone_altogether(hub, *product_ids) -> None:
    """Products the business no longer holds at all, not even deleted: only a copy of an earlier moment has them."""
    with use_hub(hub):
        ProductCategory.objects.filter(product__in=product_ids).delete()
        Product.objects.filter(pk__in=product_ids).delete()


def said(row) -> tuple[str, list[dict]]:
    """``row``'s status and what each app gave back, by the keys these tests read."""
    keys = ("app", "restored", "created", "not_created", "reasons", "refused")
    row = fresh(row)
    return row.status, [{key: result[key] for key in keys} for result in row.results]


@pytest.mark.usefixtures("no_test_fallback")
class TestProductsComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with two categories and three products made by their screen's operations, and their ids."""
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

    def test_a_deleted_product_comes_back_the_same_and_one_no_longer_held_is_created(self, recoveries, every_app_on):
        hub, ids, desserts = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        for name in ("coffee", "tea", "cake"):
            run_in(hub, "inventory.product.delete", id=ids[name])
        run_in(hub, "inventory.category.delete", id=desserts)
        gone_altogether(hub, ids["cake"])
        restored, created = (events_named(hub, f"inventory.product.{fact}") for fact in ("restored", "created"))
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        # Created: the category the business deleted, and the product no longer held.
        assert said(row) == (
            "done",
            [{"app": "inventory", "restored": 2, "created": 2, "not_created": 0, "reasons": [], "refused": ""}],
        )
        # The deleted ones, the same products, active and on sale again, with the stock their movements left; the one
        # no longer held, created in its category, which came back just before it, with no stock: a count says today's.
        assert live_products(hub) == [
            ("Cake", "CAK-1", True, Decimal("0.000"), ["Desserts"]),
            ("Coffee", "COF-1", True, Decimal("12.000"), ["Drinks"]),
            ("Tea", "TEA-1", True, Decimal("0.000"), ["Drinks"]),
        ]
        assert events_named(hub, "inventory.product.restored") == restored + 2
        assert events_named(hub, "inventory.product.created") == created + 1
        with use_hub(hub):
            back = dict(Product.objects.filter(is_deleted=False).values_list("sku", "pk"))
            assert (back["COF-1"], back["TEA-1"]) == (ids["coffee"], ids["tea"])
            assert back["CAK-1"] != ids["cake"]
            # Every movement hangs from the product that came back, as it did before it was deleted.
            assert list(StockMovement.objects.values_list("product_id", "movement_type", "qty")) == [
                (ids["coffee"], "initial", Decimal("12.000"))
            ]

    def test_a_deleted_category_comes_back_with_the_products_that_come_back_in_it(self, recoveries, every_app_on):
        hub, ids, desserts = self.a_business(recoveries, every_app_on)
        tax = a_tax_key(hub)
        run_in(hub, "inventory.category.update", id=desserts, icon="ion:ice-cream-outline", color="#cc0066", order=3)
        flan = run_in(hub, "inventory.product.create", name="Flan", sku="FLA-1", price=350, tax_category_key=tax,
                      category_ids=[desserts]).id
        run_in(hub, "inventory.product.create", name="Brownie", sku="BRO-1", price=300, tax_category_key=tax,
               category_ids=[desserts])
        copy = recoveries.copy_of(hub)
        run_in(hub, "inventory.product.delete", id=flan)
        run_in(hub, "inventory.product.delete", id=ids["cake"])
        run_in(hub, "inventory.category.delete", id=desserts)
        gone_altogether(hub, ids["cake"])
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        assert said(row) == (
            "done",
            [{"app": "inventory", "restored": 1, "created": 2, "not_created": 0, "reasons": [], "refused": ""}],
        )
        with use_hub(hub):
            back = Category.objects.get(name="Desserts", is_deleted=False)
            # A new one, as the screen creates it, with what it had; the deleted one stays deleted.
            assert back.pk != desserts
            assert (back.slug, back.icon, back.color, back.order) == ("desserts", "ion:ice-cream-outline", "#cc0066", 3)
            assert Category.objects.get(pk=desserts).is_deleted is True
            assert Product.objects.get(sku="FLA-1").pk == flan
        # In it, what came back: the deleted one, the same product, and the one no longer held, made again. The one the
        # business kept live stays as it is, out of it since the deletion.
        assert live_products(hub) == [
            ("Brownie", "BRO-1", True, Decimal("0.000"), []),
            ("Cake", "CAK-1", True, Decimal("0.000"), ["Desserts"]),
            ("Coffee", "COF-1", True, Decimal("12.000"), ["Drinks"]),
            ("Flan", "FLA-1", True, Decimal("0.000"), ["Desserts"]),
            ("Tea", "TEA-1", False, Decimal("0.000"), ["Drinks"]),
        ]

        again = recoveries.ask(copy, "inventory")
        assert run() == 1

        assert said(again) == (
            "done",
            [{"app": "inventory", "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": ""}],
        )
        with use_hub(hub):
            assert Category.objects.filter(name="Desserts", is_deleted=False).count() == 1

    def test_asked_again_nothing_is_made_twice_and_what_the_business_has_stays(self, recoveries, every_app_on):
        hub, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "inventory.product.delete", id=ids["coffee"])
        run_in(hub, "inventory.product.delete", id=ids["cake"])
        gone_altogether(hub, ids["cake"])
        recoveries.ask(copy, "inventory")
        assert run() == 1
        before = [events_named(hub, f"inventory.product.{fact}") for fact in ("restored", "created")]

        again = recoveries.ask(copy, "inventory")
        assert run() == 1

        assert said(again) == (
            "done",
            [{"app": "inventory", "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": ""}],
        )
        assert [events_named(hub, f"inventory.product.{fact}") for fact in ("restored", "created")] == before
        assert [one[0] for one in live_products(hub)] == ["Cake", "Coffee", "Tea"]

    def test_a_deleted_product_made_again_by_hand_since_stays_as_the_business_made_it(self, recoveries, every_app_on):
        hub, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        run_in(hub, "inventory.product.delete", id=ids["coffee"])
        again = run_in(hub, "inventory.product.create", name="Coffee beans", sku="COF-1", price=300,
                       tax_category_key=a_tax_key(hub)).id
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        assert said(row) == (
            "done",
            [{"app": "inventory", "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": ""}],
        )
        with use_hub(hub):
            assert dict(Product.objects.filter(sku="COF-1").values_list("pk", "is_deleted")) == {
                ids["coffee"]: True,
                again: False,
            }

    def test_a_product_whose_tax_category_the_create_refuses_is_counted_with_why(self, recoveries, every_app_on):
        hub, ids, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        gone_altogether(hub, ids["tea"], ids["cake"])
        with use_hub(hub):
            # Taxes never deletes a tax category; one no longer active is one the create does not take.
            TaxCategory.objects.filter(key=a_tax_key(hub)).update(is_active=False)
        row = recoveries.ask(copy, "inventory")

        assert run() == 1

        _, [result] = said(row)
        assert (result["restored"], result["created"], result["not_created"], result["refused"]) == (0, 0, 2, "")
        assert {one["id"] for one in result["reasons"]} == {str(ids["tea"]), str(ids["cake"])}
        assert all(one["reason"].startswith("invalid_field: ") for one in result["reasons"])
