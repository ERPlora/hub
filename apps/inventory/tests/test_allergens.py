"""INVENTORY-F35: a product declares its allergens, of the fourteen that must be declared, by the same create, change,
import and export as the rest of its data; the catalogs the till and Kitchen read carry them (INVENTORY-F27)."""

import json
import uuid

import pytest
from django.db import connections
from django.utils import translation
from live.operations import get

from apps.flow.tests.test_api import post
from apps.inventory import events
from live.assistant.running import invalid_arguments

from apps.inventory.models import Product
from apps.inventory.schemas import ForSaleListIn, ProductFiltersIn, ProductIn, ProductListIn, ProductPatchIn, ProductRefIn
from apps.inventory.tests.test_assistant_card_records import fields_of
from apps.inventory.tests.test_queries import read_csv
from apps.inventory.tests.test_services import (
    TAX,
    create,
    import_products,
    listen,
    outbox,
    received,
    row,
    run,
    update,
)
from apps.tax.models import TaxCategory
from base.tenancy.context import current_alias, use_hub

from .conftest import HOST, A, B, HUB_DB, HUB_DB_COMMITTED, ctx_for

pytestmark = HUB_DB
#: The fixture taken from the service tests: the sessions that hear each business.
__all__ = ["listen"]

NOT_ONE_OF_THE_FOURTEEN = {
    "en": "That allergen is not one of the fourteen that must be declared.",
    "es": "Ese alérgeno no es uno de los catorce de declaración obligatoria.",
}


@pytest.fixture(autouse=True)
def general(db):
    """The tax category every product here takes."""
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})[0]


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", role="hub_admin"))
    return client


# The product keeps them


def test_a_product_has_no_allergens_until_it_declares_them():
    product = create("Water")
    assert product.allergens == []
    assert Product.objects.get(pk=product.id).allergens == []


def test_a_product_written_by_code_that_does_not_know_the_allergens_has_none():
    """Expand/contract: while a deploy rolls, a process still on the previous code inserts products without the
    column; the database gives it its default instead of refusing the row."""
    product_id = uuid.uuid7()
    with connections[current_alias()].cursor() as cursor:
        cursor.execute(
            "INSERT INTO inventory_product (id, name, sku, description, product_type, price, cost, stock,"
            " low_stock_threshold, unit, price_quantity, pricing_unit, is_active, is_deleted, created_at,"
            " updated_at, created_by, updated_by) VALUES (%s, 'Old', 'OLD-1', '', 'physical', 100, 0, 0, 10,"
            " 'ud', 1, 'ud', true, false, now(), now(), '', '')",
            [product_id],
        )
    assert Product.objects.get(pk=product_id).allergens == []


def test_the_create_keeps_each_allergen_once_in_the_order_of_the_list():
    burger = create("Burger", allergens=["milk", "gluten", "milk"])
    assert burger.allergens == ["gluten", "milk"]
    assert Product.objects.get(pk=burger.id).allergens == ["gluten", "milk"]


def test_a_change_sets_them_and_inventory_tells_of_it_as_of_any_other_change():
    burger = create("Burger")
    changed = update(burger.id, allergens=["sesame", "gluten"])
    assert changed.allergens == ["gluten", "sesame"]
    assert Product.objects.get(pk=burger.id).allergens == ["gluten", "sesame"]
    assert [name for name, _payload in outbox(events.PRODUCT_UPDATED)] == [events.PRODUCT_UPDATED]


def test_a_change_that_does_not_send_them_leaves_them_and_an_empty_list_clears_them():
    burger = create("Burger", allergens=["gluten"])
    assert update(burger.id, price=900).allergens == ["gluten"]
    assert update(burger.id, allergens=[]).allergens == []


def test_sending_the_same_allergens_again_changes_nothing_and_tells_nothing():
    burger = create("Burger", allergens=["gluten", "milk"])
    update(burger.id, allergens=["milk", "gluten"])
    assert outbox(events.PRODUCT_UPDATED) == []


# Refused off the list, by the API and the assistant as by the screen


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_api_refuses_an_allergen_off_the_list_on_its_field_and_creates_nothing(admin_client, language):
    product = {"name": "Burger", "sku": "BUR", "price": 900, "tax_category_key": TAX, "allergens": ["gluten", "nuts"]}
    response = admin_client.post(
        "/api/inventory/products",
        json.dumps(product),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE=language,
    )
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (422, "invalid_payload")
    assert error["fields"] == {"allergens": NOT_ONE_OF_THE_FOURTEEN[language]}
    assert not Product.objects.exists()


def test_the_api_refuses_a_change_off_the_list_and_keeps_the_allergens_it_had(admin_client):
    burger = create("Burger", allergens=["gluten"])
    response = post(admin_client, "/inventory/products/update", {"id": str(burger.id), "allergens": ["shellfish"]})
    assert (response.status_code, set(response.json()["error"]["fields"])) == (422, {"allergens"})
    assert Product.objects.get(pk=burger.id).allergens == ["gluten"]


def test_an_employee_who_only_sees_products_reads_them_but_does_not_change_them(client, make_user):
    burger = create("Burger", allergens=["gluten"])
    client.force_login(make_user("ana", role="hub_employee"))
    read = client.get("/api/inventory/products/detail", {"id": str(burger.id)}, HTTP_HOST=HOST)
    changed = post(client, "/inventory/products/update", {"id": str(burger.id), "allergens": []})
    assert (read.status_code, read.json()["allergens"]) == (200, ["gluten"])
    assert (changed.status_code, changed.json()["error"]["code"]) == (403, "permission_denied")


def test_the_assistant_hears_the_refusal_before_any_card_is_drawn():
    burger = create("Burger")
    refused = invalid_arguments(get("inventory.product.update"), {"id": str(burger.id), "allergens": ["shellfish"]})
    assert (refused.outcome, refused.code) == ("error", "invalid_payload")
    assert "allergens" in json.loads(refused.content)["error"]["fields"]


def test_the_assistants_card_says_the_allergens_by_their_names_in_spanish():
    burger = Product.objects.create(name="Hamburguesa", sku="HAM", price=900)
    fields = fields_of("inventory.product.update", {"id": str(burger.id), "allergens": ["milk", "gluten"]}, "es")
    assert (fields["allergens"]["label"], fields["allergens"]["value"]) == ("Alérgenos", ["Leche", "Gluten"])


# The catalogs the till and Kitchen read (INVENTORY-F27)


def test_the_product_and_the_list_the_till_and_kitchen_read_carry_its_allergens():
    burger = create("Burger", allergens=["milk", "gluten"])
    assert run("inventory.product.get", ProductRefIn(id=burger.id)).allergens == ["gluten", "milk"]
    assert [one.allergens for one in run("inventory.product.list", ProductListIn()).rows] == [["gluten", "milk"]]


def test_the_sale_catalog_carries_the_allergens_of_each_product():
    create("Burger", allergens=["egg", "gluten"])
    create("Water")
    rows = run("inventory.product.list_for_sale", ForSaleListIn()).rows
    assert {one.name: one.allergens for one in rows} == {"Burger": ["gluten", "egg"], "Water": []}


# The CSV (INVENTORY-F11, INVENTORY-F09)


@pytest.mark.parametrize(
    ("language", "delimiter", "header", "names"),
    [("en", ",", "Allergens", "Gluten, Milk"), ("es", ";", "Alérgenos", "Gluten, Leche")],
)
def test_the_export_carries_the_allergens_column_by_their_names(language, delimiter, header, names):
    create("Burger", allergens=["milk", "gluten"])
    create("Water")
    with translation.override(language):
        export = run("inventory.product.export", ProductFiltersIn())
    headers, burger, water = read_csv(export, delimiter)
    column = headers.index(header)
    assert (burger[column], water[column]) == (names, "")


def test_the_allergens_column_comes_after_the_description_as_in_the_form():
    with translation.override("en"):
        headers = read_csv(run("inventory.product.export", ProductFiltersIn()), ",")[0]
    assert headers[headers.index("Description") + 1] == "Allergens"


@pytest.mark.parametrize("cell", ["Leche, gluten", "MILK,Gluten", "gluten , leche ,"])
def test_an_import_reads_the_allergens_in_spanish_or_english_in_any_case(cell):
    report = import_products(row("BUR", allergens=cell))
    assert report.created == 1
    assert Product.objects.get(sku="BUR").allergens == ["gluten", "milk"]


def test_an_import_reads_the_allergens_with_or_without_accents():
    import_products(row("GAM", allergens="Crustaceos, Moluscos"), row("PAN", allergens="Sésamo, frutos de cascara"))
    assert Product.objects.get(sku="GAM").allergens == ["crustaceans", "molluscs"]
    assert Product.objects.get(sku="PAN").allergens == ["tree_nuts", "sesame"]


@pytest.mark.parametrize(
    ("language", "reason"),
    [("en", "Allergen not recognized: marisco"), ("es", "Alérgeno no reconocido: marisco")],
)
def test_an_allergen_the_import_does_not_recognize_fails_its_row_and_only_it(language, reason):
    with translation.override(language):
        report = import_products(row("BUR", allergens="Gluten, marisco"), row("TEA"))
    assert [(one.key, one.status, one.reason) for one in report.rows] == [
        ("BUR", "failed", reason),
        ("TEA", "created", ""),
    ]
    assert list(Product.objects.values_list("sku", flat=True)) == ["TEA"]


def test_the_rehearsal_says_the_same_about_an_allergen_and_creates_nothing():
    report = import_products(row("BUR", allergens="marisco"), dry_run=True)
    assert [(one.status, one.reason) for one in report.rows] == [("failed", "Allergen not recognized: marisco")]
    assert not Product.objects.exists()


def test_an_imported_sku_that_already_exists_is_skipped_and_keeps_its_allergens():
    create("Burger", sku="BUR", allergens=["gluten"])
    report = import_products(row("BUR", allergens="Leche"))
    assert [one.status for one in report.rows] == ["skipped"]
    assert Product.objects.get(sku="BUR").allergens == ["gluten"]


def test_the_export_imports_back_with_its_allergens():
    create("Burger", sku="BUR", allergens=["milk", "gluten"])
    with translation.override("es"):
        headers, burger = read_csv(run("inventory.product.export", ProductFiltersIn()), ";")
    Product.objects.all().delete()
    cells = dict(zip(headers, burger, strict=True))
    import_products(row("BUR", allergens=cells["Alérgenos"]))
    assert Product.objects.get(sku="BUR").allergens == ["gluten", "milk"]


# Each business its own


@HUB_DB_COMMITTED
def test_allergens_declared_in_business_b_tell_b_only_and_stay_in_b(listen, hub_b):
    with use_hub(hub_b):
        TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
        burger = get("inventory.product.create")(
            ctx_for("hub_admin", B), ProductIn(name="Burger", sku="BUR", price=1, tax_category_key=TAX)
        )
        on_a, on_b = listen(A), listen(B)
        get("inventory.product.update")(ctx_for("hub_admin", B), ProductPatchIn(id=burger.id, allergens=["gluten"]))
        assert Product.objects.get(pk=burger.id).allergens == ["gluten"]

    assert received(on_b, stop_after=1) == [{"events": [events.PRODUCT_UPDATED]}]
    assert received(on_a, timeout=0.3) == []
    assert not Product.objects.filter(sku="BUR").exists()
