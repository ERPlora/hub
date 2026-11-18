"""What a product's row of a backup or a template carries only when the product has it — its image and its allergens —
and how a file brings them back into a business (``base.blueprint_products``).

A product's allergens travel by their codes, as Inventory keeps them, and load through Inventory's own import, which
reads them; a file made before products had allergens loads its products without any.
"""

from django.contrib.auth import get_user_model
from live.context import OperationContext

from apps.inventory.models import Product
from apps.tax.models import TaxCategory
from base import blueprint
from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, B, in_business_a
from base.tests.test_blueprint import call, ctx, manifest, owner

#: The fixtures taken from the blueprint tests: business A entered, its owner and their context.
__all__ = ["ctx", "in_business_a", "owner"]
pytestmark = HUB_DB

BURGER = {"name": "Hamburguesa", "sku": "HAM-01", "price": 1200, "tax_category_key": "restaurant.food"}
#: A product's row as a file made before products had allergens writes it.
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
    return blueprint.export_data(ctx, {"inventory": ["inventory.product"]}, purpose=purpose)["inventory.product"]


def load(ctx, rows, purpose="backup"):
    bundle = blueprint.Bundle(manifest=manifest(purpose=purpose), data={"inventory.product": rows})
    return blueprint.apply(ctx, bundle, apps=None)


def products_report(result):
    inventory = next(app for app in result.report["apps"] if app["id"] == "inventory")
    return next(dataset for dataset in inventory["datasets"] if dataset["key"] == "inventory.product")


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
        TaxCategory.objects.get_or_create(key="restaurant.food", defaults={"name": "Comida"})
        user = get_user_model().objects.create_user(username="bea", password="pw")
        Membership.objects.create(user=user, host=B.key, role=Membership.Role.OWNER)
        theirs = OperationContext(scope=B, actor=user, permissions=permissions_for(user, B), language="es")
        result = load(theirs, exported)
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
