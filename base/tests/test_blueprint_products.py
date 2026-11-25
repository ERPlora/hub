"""What a product's row of a backup or a template carries only when the product has it — its image, its allergens and
being hidden from the website — and how a file brings them back into a business (``base.blueprint_products``).

A product's allergens travel by their codes, as Inventory keeps them, and load through Inventory's own import, which
reads them; a file made before products had allergens loads its products without any. A product hidden from the
website comes back hidden, and a file that does not say so loads its products visible.
"""

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


def test_a_file_of_several_pages_hides_only_the_product_it_names(ctx):
    rows = [{**OLD_ROW, "name": f"Tapa {number}", "sku": f"TAP-{number:03}"} for number in range(103)]
    rows[101]["show_on_website"] = False

    assert products_report(load(ctx, rows))["created"] == 103

    assert list(Product.objects.filter(show_on_website=False).values_list("sku", flat=True)) == ["TAP-101"]


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
