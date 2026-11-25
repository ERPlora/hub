"""What a product's row of a backup or a template carries only when the product has it — its image, its allergens,
being hidden from the website, being a service and what its price refers to — and how a file brings them back into a
business (``base.blueprint_products``).

A product's allergens travel by their codes, as Inventory keeps them, and load through Inventory's own import, which
reads them, as it reads the type and what the price refers to; a file that does not say them loads its products
without allergens, physical and priced by one of their unit. A product hidden from the website comes back hidden, and
a file that does not say so loads its products visible.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from live import operations
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import get

from apps.inventory.models import Product
from apps.tax.models import TaxCategory
from base import blueprint, blueprint_products
from base.models import Membership
from base.permissions import access_for
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, B, in_business_a
from base.tests.test_blueprint import call, ctx, manifest, owner

#: The fixtures taken from the blueprint tests: business A entered, its owner and their context.
__all__ = ["ctx", "in_business_a", "owner"]
pytestmark = HUB_DB

BURGER = {"name": "Hamburguesa", "sku": "HAM-01", "price": 1200, "tax_category_key": "restaurant.food"}
STAFF_MEAL = {**BURGER, "name": "Comida del personal", "sku": "STAFF-01", "show_on_website": False}
DELIVERY = {**BURGER, "name": "Reparto", "sku": "REP-01", "price": 300, "product_type": "service"}
#: Sold by weight: 2,50 € per 100 g, and 40,00 € per kilo of a product kept in grams.
HAM = {**BURGER, "name": "Jamón", "sku": "JAM-01", "price": 250, "unit": "g", "price_quantity": 100, "pricing_unit": "g"}
SAFFRON = {**BURGER, "name": "Azafrán", "sku": "AZA-01", "price": 4000, "unit": "g", "pricing_unit": "kg"}
#: A product's row as a file made before products had allergens, or could be hidden from the website, writes it.
OLD_ROW = {
    "name": "Croquetas",
    "sku": "ENT-01",
    "price": 850,
    "cost": 0,
    "stock": "",
    "low_stock_threshold": "",
    "unit": "ud",
    "ean13": "",
    "description": "",
    "tax_category_key": "restaurant.food",
    "categories": [],
}


def exported_products(ctx, purpose="backup"):
    return blueprint.export.export_data(ctx, {"inventory": ["inventory.product"]}, purpose=purpose)["inventory.product"]


def load(ctx, rows, purpose="backup"):
    bundle = blueprint.archive.Bundle(manifest=manifest(purpose=purpose), data={"inventory.product": rows})
    return blueprint.loading.apply(ctx, bundle, apps=None)


def products_report(result):
    inventory = next(app for app in result.report["apps"] if app["id"] == "inventory")
    return next(dataset for dataset in inventory["datasets"] if dataset["key"] == "inventory.product")


def owner_of_b():
    """The owner of business B, whose tax categories are the burger's; business B entered."""
    TaxCategory.objects.get_or_create(key="restaurant.food", defaults={"name": "Comida"})
    user = get_user_model().objects.create_user(username="bea", password="pw")
    Membership.objects.create(user=user, host=B.key, role=Membership.Role.OWNER)
    return OperationContext(scope=B, actor=user, permissions=access_for(user, B), language="es")


def on_the_website(ctx):
    """The products the public menu reads: the ones on sale the business shows on its website."""
    rows = call(ctx, "inventory.product.list_for_sale", limit=100, show_on_website=True).rows
    return sorted(row.sku for row in rows)


#: Of a product, what is not the business's own data of it: its identity, its bin, who touched it and when, and the
#: day's «sold out», which another day's product is not born with (INVENTORY-F34).
NOT_ITS_OWN_DATA = {
    "id", "is_sold_out", "is_deleted", "deleted_at", "created_at", "updated_at", "created_by", "updated_by",
}  # fmt: skip


def own_data(product):
    return {
        field.name: getattr(product, field.attname)
        for field in Product._meta.concrete_fields
        if field.name not in NOT_ITS_OWN_DATA
    }


def products_by_sku():
    return {product.sku: own_data(product) for product in Product.objects.filter(is_deleted=False)}


def deleted_and_loaded(ctx):
    """Every product of the business exported, deleted and loaded again: the report of the load."""
    exported = exported_products(ctx)
    for product in call(ctx, "inventory.product.list", limit=100).rows:
        call(ctx, "inventory.product.delete", id=product.id)
    assert products_by_sku() == {}
    return products_report(load(ctx, exported))


def test_every_datum_of_a_product_comes_back_as_it_was(ctx):
    marked = {
        "ean13": "8412345678905", "description": "De bellota", "allergens": ["milk"], "cost": 130, "initial_stock": 5000,
        "low_stock_threshold": 500, "track_stock": True, "is_active": False, "show_on_website": False,
    }  # fmt: skip
    call(ctx, "inventory.product.create", **{**HAM, **marked, "pricing_unit": "kg", "price_quantity": "0.1"})
    call(ctx, "inventory.product.create", **DELIVERY)
    before = products_by_sku()
    born = own_data(Product())
    # What no product here has its own way would come back equal even if it were lost: only the image, whose own tests
    # are in test_blueprint_images.py.
    assert {name for name in born if all(data[name] == born[name] for data in before.values())} == {"image"}

    assert deleted_and_loaded(ctx)["status"] == "applied"

    assert products_by_sku() == before


def test_a_backup_and_a_template_say_which_products_are_services_and_what_their_price_refers_to(ctx):
    for product in (BURGER, DELIVERY, HAM, SAFFRON):
        call(ctx, "inventory.product.create", **product)
    for purpose in ("backup", "template"):
        rows = {row["sku"]: row for row in exported_products(ctx, purpose)}
        said = {
            sku: {key: row[key] for key in ("product_type", "price_quantity", "pricing_unit") if key in row}
            for sku, row in rows.items()
        }
        assert said == {
            "HAM-01": {},
            "REP-01": {"product_type": "service"},
            "JAM-01": {"price_quantity": "100"},
            "AZA-01": {"pricing_unit": "kg"},
        }, purpose


def test_services_and_prices_by_another_quantity_come_back_so_in_another_business(ctx, hub_b):
    for product in (BURGER, DELIVERY, HAM, SAFFRON):
        call(ctx, "inventory.product.create", **product)
    exported = exported_products(ctx, "template")

    with use_hub(hub_b):
        assert products_report(load(owner_of_b(), exported, "template"))["status"] == "applied"
        rows = Product.objects.values_list("sku", "product_type", "price", "price_quantity", "pricing_unit")
        assert {sku: tuple(rest) for sku, *rest in rows} == {
            "HAM-01": ("physical", 1200, 1, "ud"),
            "REP-01": ("service", 300, 1, "ud"),
            "JAM-01": ("physical", 250, 100, "g"),
            "AZA-01": ("physical", 4000, 1, "kg"),
        }


def charged(ctx, sku, quantity, key):
    """What the till charges, by card, for ``quantity`` of the product ``sku``."""
    order = call(ctx, "sale.order.open", lines=[{"product": sku, "quantity": quantity}])
    payments = [{"method": "card"}]
    return call(ctx, "sale.sale.complete", order_id=order.id, idempotency_key=key, payments=payments).total


def test_a_product_sold_by_weight_is_charged_what_it_was_after_its_backup_is_loaded(ctx):
    for product in (HAM, SAFFRON):
        call(ctx, "inventory.product.create", **product)
    assert (charged(ctx, "JAM-01", "300", "before-ham-01"), charged(ctx, "AZA-01", "5", "before-saffron-01")) == (750, 20)

    data = blueprint.export.export_data(ctx, {"inventory": ["inventory.product"]}, purpose="backup")
    file = blueprint.archive.write_zip(blueprint.archive.Bundle(manifest=manifest(purpose="backup"), data=data))
    for product in call(ctx, "inventory.product.list", limit=100).rows:
        call(ctx, "inventory.product.delete", id=product.id)
    result = blueprint.loading.apply(ctx, blueprint.archive.read_zip(file), apps=None)

    assert products_report(result)["created"] == 2
    assert (charged(ctx, "JAM-01", "300", "after-ham-0001"), charged(ctx, "AZA-01", "5", "after-saffron-01")) == (750, 20)


def test_a_service_that_comes_back_still_keeps_no_stock(ctx):
    call(ctx, "inventory.product.create", **DELIVERY)
    assert deleted_and_loaded(ctx)["created"] == 1
    [made] = call(ctx, "inventory.product.list", limit=100).rows
    assert (made.product_type, made.tracks_stock) == ("service", False)


def test_a_product_sold_below_zero_comes_back_with_its_stock(ctx):
    call(ctx, "inventory.config.update", allow_sell_without_stock=True)
    burger = call(ctx, "inventory.product.create", **BURGER, initial_stock=2)
    call(ctx, "inventory.stock.write_off", product_id=burger.id, qty=5, reason="Se quemaron en la plancha")

    report = deleted_and_loaded(ctx)

    assert (report["status"], report["created"], report["failed"], report["problems"]) == ("applied", 1, 0, [])
    assert Product.objects.get(sku="HAM-01", is_deleted=False).stock == Decimal("-3")


def test_a_file_that_does_not_say_them_loads_physical_products_priced_by_one_of_their_unit(ctx):
    rows = [{**OLD_ROW, "unit": "g"}, {**OLD_ROW, "name": "Agua", "sku": "BEB-01", "unit": ""}]
    rows += [{**OLD_ROW, "sku": "ENT-02", "product_type": None, "price_quantity": "", "pricing_unit": None}]

    assert products_report(load(ctx, rows))["created"] == 3

    made = Product.objects.order_by("sku")
    assert list(made.values_list("sku", "product_type", "price", "price_quantity", "pricing_unit")) == [
        ("BEB-01", "physical", 850, 1, "ud"),
        ("ENT-01", "physical", 850, 1, "g"),
        ("ENT-02", "physical", 850, 1, "ud"),
    ]


@pytest.mark.parametrize(
    ("written", "reason"),
    [
        ({"product_type": "combo"}, "Tipo de producto no reconocido: combo"),
        ({"product_type": "service", "stock": "3"}, "Un servicio no lleva stock."),
        ({"price_quantity": 0}, "Cantidad no numérica"),
        ({"price_quantity": [100]}, "Cantidad no numérica"),
        ({"pricing_unit": "kg"}, "El precio tiene que referirse a una unidad del mismo tipo que la del producto."),
    ],
)
def test_a_row_whose_type_or_price_quantity_cannot_be_fails_alone_with_its_reason(ctx, written, reason):
    """Never a product at another price: the row is refused whole, told by its name, and the rest loads."""
    report = products_report(load(ctx, [{**OLD_ROW, **written}, {**OLD_ROW, "name": "Agua", "sku": "BEB-01"}]))

    assert (report["created"], report["failed"], report["problems"]) == (1, 1, [f"«Croquetas»: {reason}"])
    assert list(Product.objects.values_list("sku", flat=True)) == ["BEB-01"]


def test_a_price_quantity_written_as_a_number_loads_as_it_is(ctx):
    rows = [{**OLD_ROW, "unit": "g", "price_quantity": 100}, {**OLD_ROW, "sku": "ENT-02", "unit": "kg", "price_quantity": 0.5}]
    assert products_report(load(ctx, rows))["created"] == 2
    quantities = dict(Product.objects.values_list("sku", "price_quantity"))
    assert quantities == {"ENT-01": 100, "ENT-02": Decimal("0.5")}


def test_a_product_the_business_already_has_keeps_its_own_type_and_price_quantity(ctx):
    call(ctx, "inventory.product.create", **HAM)
    rows = [{**OLD_ROW, "name": "Jamón", "sku": "JAM-01", "product_type": "service", "price_quantity": "1"}]
    assert products_report(load(ctx, rows))["status"] == "already"
    kept = Product.objects.get(sku="JAM-01")
    assert (kept.product_type, kept.price_quantity) == ("physical", 100)


def test_a_backup_and_a_template_carry_the_allergens_of_a_product_by_their_codes(ctx):
    call(ctx, "inventory.product.create", **BURGER, allergens=["milk", "gluten"])
    for purpose in ("backup", "template"):
        [row] = exported_products(ctx, purpose)
        assert row["allergens"] == ["gluten", "milk"], purpose


def test_a_product_without_allergens_or_image_travels_without_those_keys(ctx):
    call(ctx, "inventory.product.create", **BURGER)
    [row] = exported_products(ctx)
    assert {"allergens", "image"}.isdisjoint(row)


def test_a_product_with_an_image_still_carries_it(ctx):
    made = call(ctx, "inventory.product.create", **BURGER)
    Product.objects.filter(pk=made.id).update(image="catalog:hospitality/hamburguesa")
    [row] = exported_products(ctx)
    assert row["image"] == "catalog:hospitality/hamburguesa"


def test_what_a_backup_carries_loads_into_another_business_with_the_same_allergens(ctx, hub_b):
    call(ctx, "inventory.product.create", **BURGER, allergens=["milk", "gluten"])
    exported = exported_products(ctx)

    with use_hub(hub_b):
        result = load(owner_of_b(), exported)
        assert products_report(result)["created"] == 1
        assert Product.objects.get(sku="HAM-01").allergens == ["gluten", "milk"]


def test_a_file_made_before_products_had_allergens_loads_them_without_any(ctx):
    result = load(ctx, [OLD_ROW])
    assert products_report(result)["created"] == 1
    assert Product.objects.get(sku="ENT-01").allergens == []


def test_a_file_may_name_the_allergens_in_words(ctx):
    load(ctx, [{**OLD_ROW, "allergens": "Leche, gluten"}])
    assert Product.objects.get(sku="ENT-01").allergens == ["gluten", "milk"]


def test_a_row_with_an_allergen_off_the_list_fails_alone_with_its_reason(ctx):
    result = load(ctx, [{**OLD_ROW, "allergens": ["gluten", "shellfish"]}, {**OLD_ROW, "name": "Agua", "sku": "BEB-01"}])
    report = products_report(result)
    assert (report["created"], report["failed"]) == (1, 1)
    assert report["problems"] == ["«Croquetas»: Alérgeno no reconocido: shellfish"]
    assert list(Product.objects.values_list("sku", flat=True)) == ["BEB-01"]


def test_allergens_that_are_not_a_list_or_a_text_load_the_product_without_any(ctx):
    load(ctx, [{**OLD_ROW, "allergens": {"gluten": True}}])
    assert Product.objects.get(sku="ENT-01").allergens == []


def test_a_list_with_something_that_is_not_an_allergen_fails_its_row_instead_of_dropping_it(ctx):
    report = products_report(load(ctx, [{**OLD_ROW, "allergens": ["gluten", 7]}]))
    assert (report["created"], report["problems"]) == (0, ["«Croquetas»: Alérgeno no reconocido: 7"])


def test_a_backup_and_a_template_say_which_products_are_hidden_from_the_website(ctx):
    call(ctx, "inventory.product.create", **BURGER)
    call(ctx, "inventory.product.create", **STAFF_MEAL)
    for purpose in ("backup", "template"):
        rows = {row["sku"]: row for row in exported_products(ctx, purpose)}
        assert rows["STAFF-01"]["show_on_website"] is False, purpose
        assert "show_on_website" not in rows["HAM-01"], purpose


def test_a_hidden_product_deleted_and_loaded_from_its_backup_is_still_hidden(ctx):
    call(ctx, "inventory.product.create", **BURGER)
    staff_meal = call(ctx, "inventory.product.create", **STAFF_MEAL)
    exported = exported_products(ctx)
    call(ctx, "inventory.product.delete", id=staff_meal.id)

    assert products_report(load(ctx, exported))["created"] == 1

    assert Product.objects.get(sku="STAFF-01", is_deleted=False).show_on_website is False
    assert on_the_website(ctx) == ["HAM-01"]


def test_another_business_that_loads_the_file_hides_the_same_products(ctx, hub_b):
    call(ctx, "inventory.product.create", **BURGER)
    call(ctx, "inventory.product.create", **STAFF_MEAL)
    exported = exported_products(ctx, "template")

    with use_hub(hub_b):
        theirs = owner_of_b()
        assert products_report(load(theirs, exported, "template"))["created"] == 2
        assert on_the_website(theirs) == ["HAM-01"]
        assert dict(Product.objects.values_list("sku", "show_on_website")) == {"HAM-01": True, "STAFF-01": False}


def test_a_file_that_does_not_say_a_product_is_hidden_loads_it_visible(ctx):
    assert products_report(load(ctx, [OLD_ROW]))["created"] == 1
    assert Product.objects.get(sku="ENT-01").show_on_website is True


@pytest.mark.parametrize("written", [True, None, 0, "", "false"])
def test_only_a_clear_no_hides_a_product(ctx, written):
    assert products_report(load(ctx, [{**OLD_ROW, "show_on_website": written}]))["created"] == 1
    assert Product.objects.get(sku="ENT-01").show_on_website is True


def test_a_product_the_business_already_has_keeps_its_own_mark(ctx):
    call(ctx, "inventory.product.create", **BURGER)
    rows = [{**OLD_ROW, "name": "Hamburguesa", "sku": "HAM-01", "show_on_website": False}]
    assert products_report(load(ctx, rows))["status"] == "already"
    assert on_the_website(ctx) == ["HAM-01"]


def test_a_file_of_several_pages_hides_only_the_products_it_names(ctx):
    rows = [{**OLD_ROW, "name": f"Tapa {number}", "sku": f"TAP-{number:03}"} for number in range(103)]
    rows[3]["show_on_website"] = rows[101]["show_on_website"] = False

    assert products_report(load(ctx, rows))["created"] == 103

    hidden = Product.objects.filter(show_on_website=False).order_by("sku")
    assert list(hidden.values_list("sku", flat=True)) == ["TAP-003", "TAP-101"]


def test_a_page_the_import_refuses_is_told_row_by_row_and_the_next_page_loads(ctx):
    rows = [{**OLD_ROW, "name": f"Tapa {number}", "sku": f"TAP-{number:03}"} for number in range(101)]
    rows[1]["name"], rows[2]["description"] = "", "x" * 5000

    report = products_report(load(ctx, rows))

    assert (report["created"], report["failed"]) == (1, 100)
    assert [problem.split(":")[0] for problem in report["problems"][:3]] == ["«Tapa 0»", "«TAP-001»", "«Tapa 2»"]
    assert list(Product.objects.values_list("sku", flat=True)) == ["TAP-100"]


def test_what_the_import_does_not_take_loads_by_the_products_own_change(ctx):
    tapas = call(ctx, "inventory.category.create", name="Tapas", tax_category_key="restaurant.food")
    row = {**OLD_ROW, "categories": ["tapas"], "track_stock": True, "is_active": False, "show_on_website": False}

    assert products_report(load(ctx, [row]))["problems"] == []

    [made] = call(ctx, "inventory.product.list", limit=100).rows
    assert (made.category_ids, made.track_stock, made.is_active, made.show_on_website) == ([tapas.id], True, False, False)


class Refuses:
    """Inventory's change of a product when it refuses it."""

    input = staticmethod(get("inventory.product.update").input)

    def __call__(self, ctx, data):
        raise InvalidPayload("That change is not taken.", code="invalid_field")


def test_a_mark_inventory_refuses_is_told_and_the_rest_loads(ctx, monkeypatch):
    monkeypatch.setitem(operations.registry, "inventory.product.update", Refuses())
    rows = [{**OLD_ROW, "show_on_website": False}, {**OLD_ROW, "name": "Agua", "sku": "BEB-01"}]

    report = products_report(load(ctx, rows))

    assert (report["status"], report["created"]) == ("partial", 2)
    assert report["problems"] == ["«ENT-01»: That change is not taken."]


@pytest.mark.parametrize(
    ("row", "marks"),
    [
        ({}, {}),
        ({"track_stock": None, "is_active": True, "show_on_website": True}, {}),
        ({"track_stock": "yes", "is_active": 0, "show_on_website": "no"}, {}),
        ({"track_stock": True}, {"track_stock": True}),
        ({"track_stock": False}, {"track_stock": False}),
        ({"is_active": False}, {"is_active": False}),
        ({"show_on_website": False}, {"show_on_website": False}),
    ],
)
def test_the_marks_of_a_row_are_the_ones_that_change_a_product_just_created(row, marks):
    assert blueprint_products.marks(row) == marks


@pytest.mark.parametrize(
    ("categories", "names"),
    [(None, []), ("Tapas", []), ([], []), (["Tapas", " ", 7, None, "Vinos"], ["Tapas", "Vinos"])],
)
def test_the_categories_of_a_row_are_the_names_it_lists(categories, names):
    assert blueprint_products.category_names({"categories": categories}) == names
