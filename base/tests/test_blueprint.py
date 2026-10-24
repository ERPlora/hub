"""The blueprints' rules (``base.blueprint``; PLAN-HUB round 2026-10-21, «Blueprints»): the ``.blueprint.zip``, the
catalogue of seeds by vertical and what travels of each app.

Flows BASE-G101–G109. What travels of an app goes through that app's own operations, never its tables (hub#426): a
dataset reads its rows with the app's list and writes them with its create, so the app's rules (a SKU never twice, a
category's tax key resolved by Taxes) hold for an import too. Rows name each other by their natural key (a product's
categories by name, a table's zone by name), never by an id of the business that made the file (hub#2626). People,
PINs and fiscal data never travel: there is no dataset for them, and a file that brings one has it discarded.

Every test here runs against the real apps (inventory, service, table, customer), never a stand-in.
"""

import base64
import io
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, Scope
from live.operations import get

from base import blueprint, catalog
from base.models import Membership
from base.permissions import permissions_for

pytestmark = pytest.mark.django_db

A = Scope("host", "a")


@pytest.fixture
def owner():
    user = get_user_model().objects.create_user(username="olga", password="pw")
    Membership.objects.create(user=user, host="a", role=Membership.Role.OWNER)
    return user


@pytest.fixture
def ctx(owner):
    return OperationContext(scope=A, actor=owner, permissions=permissions_for(owner, A), language="es")


def call(ctx, operation, /, **data):
    op = get(operation)
    return op(ctx, op.input(**data))


def manifest(**fields):
    return {
        "format": blueprint.FORMAT,
        "format_version": blueprint.FORMAT_VERSION,
        "name": "Bar Pepe",
        "language": "es",
        "country": "ES",
        "purpose": "template",
        "created_at": "2026-10-24T10:00:00+00:00",
        "vertical": "restaurant",
        "version": "",
        "apps": ["inventory", "table"],
        **fields,
    }


def zipped(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def a_file(data=None, **fields) -> bytes:
    data = {"inventory.category": [{"name": "Entrantes", "tax_category_key": "restaurant.food"}]} if data is None else data
    files = {"manifest.json": json.dumps(manifest(**fields))}
    files |= {f"data/{key}.json": json.dumps(rows) for key, rows in data.items()}
    return zipped(files)


# ── The file: a .blueprint.zip (BASE-G101, BASE-G104) ──────────────────────────────────────────────────────────────


def test_a_written_file_reads_back_as_the_same_blueprint():
    bundle = blueprint.Bundle(
        manifest=manifest(), data={"inventory.category": [{"name": "Postres", "tax_category_key": "restaurant.food"}]}
    )

    read = blueprint.read_zip(blueprint.write_zip(bundle))

    assert read == bundle
    with zipfile.ZipFile(io.BytesIO(blueprint.write_zip(bundle))) as archive:
        assert sorted(archive.namelist()) == ["data/inventory.category.json", "manifest.json"]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"not a zip", "not_a_blueprint"),
        (zipped({"data/inventory.category.json": "[]"}), "no_manifest"),
        (zipped({"manifest.json": "{not json"}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest(format="something.else"))}), "not_a_blueprint"),
        (zipped({"manifest.json": json.dumps(manifest(format_version=blueprint.FORMAT_VERSION + 1))}), "too_new"),
        (zipped({"manifest.json": json.dumps(manifest(purpose="everything"))}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest(name=""))}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest()), "data/inventory.category.json": '{"rows": 1}'}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest()), "data/inventory.category.json": "[1, 2]"}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest()), "../evil.json": "[]"}), "unreadable"),
        (zipped({"manifest.json": json.dumps(manifest()), "data/../../evil.json": "[]"}), "unreadable"),
    ],
)
def test_a_file_that_is_not_a_blueprint_is_refused_with_its_reason(content, reason):
    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(content)

    assert refused.value.reason == reason
    assert str(refused.value)  # a sentence for the person, never empty


def test_a_file_too_big_is_refused_before_it_is_opened():
    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(b"0" * (blueprint.MAX_FILE_BYTES + 1))

    assert refused.value.reason == "too_big"


def test_a_zip_that_inflates_beyond_the_limit_is_refused_without_inflating_it(monkeypatch):
    monkeypatch.setattr(blueprint, "MAX_INFLATED_BYTES", 1000)
    content = a_file({"inventory.category": [{"name": "x" * 50, "tax_category_key": ""}] * 100})

    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_zip(content)

    assert refused.value.reason == "too_big"


def test_what_no_dataset_carries_is_left_out_of_the_blueprint():
    """People, PINs and fiscal data have no dataset: a file that brings them (a hand-made one, an old hub's) has them
    dropped on reading, and the blueprint says which parts it dropped."""
    content = a_file(
        {
            "inventory.category": [{"name": "Entrantes", "tax_category_key": ""}],
            "base.membership": [{"user": "ana", "role": "hub_owner", "pin": "0000"}],
            "verifactu.record": [{"nif": "B12345678"}],
        }
    )

    read = blueprint.read_zip(content)

    assert list(read.data) == ["inventory.category"]
    assert read.dropped == ["base.membership", "verifactu.record"]


# ── The catalogue: the seeds by vertical (BASE-G103) ───────────────────────────────────────────────────────────────


def test_the_catalogue_has_a_seed_of_every_vertical_in_spanish_and_in_english():
    templates = blueprint.catalog()

    assert sorted((template.vertical, template.language) for template in templates) == sorted(
        (vertical, language) for vertical in catalog.known_verticals() for language in ("es", "en")
    )
    for template in templates:
        assert template.key == f"{template.vertical}.{template.language}"
        assert template.name and template.description and template.version
        assert template.country == "ES"
        # What a seed turns on is its vertical's: every app that lists it, closed by requires (PLAN §15.2).
        assert template.bundle.manifest["apps"] == catalog.template_apps(template.vertical)
        assert blueprint.template(template.key) == template


def test_a_seed_brings_data_only_of_its_own_apps_and_never_personal_data():
    for template in blueprint.catalog():
        assert template.bundle.data, template.key
        for key, rows in template.bundle.data.items():
            dataset = blueprint.dataset(key)
            assert dataset.app in template.bundle.manifest["apps"], (template.key, key)
            assert not dataset.personal, (template.key, key)
            assert rows, (template.key, key)


def test_an_unknown_template_is_none():
    assert blueprint.template("bakery.es") is None


@pytest.mark.parametrize("key", ["restaurant.es", "restaurant.en", "hair_salon.es", "hair_salon.en"])
def test_every_seed_loads_whole_into_an_empty_business(ctx, key):
    """The seeds are data the apps accept: every row is created, none fails (INVENTORY-F12 for the menu)."""
    seed = blueprint.template(key)

    result = blueprint.apply(ctx, seed.bundle, apps=None)

    failures = [
        (app["id"], dataset["key"], dataset["problems"])
        for app in result.report["apps"]
        for dataset in app["datasets"]
        if dataset["status"] != "applied"
    ]
    assert failures == []
    assert {key: len(ids) for key, ids in result.created.items()} == {
        key: len(rows) for key, rows in seed.bundle.data.items()
    }


# ── Loading: each app by its own operations (BASE-G105) ────────────────────────────────────────────────────────────


def restaurant_bundle(**data):
    return blueprint.Bundle(
        manifest=manifest(),
        data={
            "inventory.category": [
                {"name": "Entrantes", "tax_category_key": "restaurant.food", "description": "", "icon": "ion:pizza-outline", "color": "#e67e22", "order": 1},
                {"name": "Bebidas", "tax_category_key": "restaurant.drink", "description": "", "icon": "ion:beer-outline", "color": "#3880ff", "order": 2},
            ],
            "inventory.product": [
                {"name": "Croquetas", "sku": "ENT-01", "price": 850, "cost": 0, "stock": "", "low_stock_threshold": "0", "unit": "ud", "ean13": "", "description": "Caseras", "tax_category_key": "restaurant.food", "categories": ["Entrantes"], "track_stock": False, "is_active": True},
                {"name": "Agua", "sku": "BEB-01", "price": 200, "cost": 50, "stock": "24", "low_stock_threshold": "6", "unit": "ud", "ean13": "", "description": "", "tax_category_key": "restaurant.drink", "categories": ["Bebidas"], "track_stock": None, "is_active": True},
            ],
            "table.zone": [{"name": "Terraza", "description": "", "color": "success", "sort_order": 1}],
            "table.table": [
                {"number": "T1", "name": "", "capacity": 4, "shape": "round", "zone": "Terraza"},
                {"number": "T2", "name": "Junto a la fuente", "capacity": 2, "shape": "square", "zone": "Terraza"},
            ],
            **data,
        },
    )


def test_a_blueprint_loads_each_app_through_its_operations_and_links_rows_by_name(ctx):
    result = blueprint.apply(ctx, restaurant_bundle(), apps=None)

    products = {row.sku: row for row in call(ctx, "inventory.product.list", limit=100).rows}
    categories = {row.name: row for row in call(ctx, "inventory.category.list", limit=100).rows}
    assert products["ENT-01"].price == 850
    assert products["ENT-01"].category_ids == [categories["Entrantes"].id]
    assert products["BEB-01"].category_ids == [categories["Bebidas"].id]
    assert str(products["BEB-01"].stock) in {"24", "24.000"}
    assert categories["Entrantes"].icon == "ion:pizza-outline"
    tables = {row.number: row for row in call(ctx, "table.table.list", limit=100).rows}
    assert (tables["T2"].name, tables["T2"].capacity, tables["T2"].zone_name) == ("Junto a la fuente", 2, "Terraza")
    assert sorted(result.created["inventory.product"]) == sorted([str(products["ENT-01"].id), str(products["BEB-01"].id)])
    assert [app["id"] for app in result.report["apps"]] == ["inventory", "table"]
    assert {app["status"] for app in result.report["apps"]} == {"applied"}


def test_loading_again_duplicates_nothing_and_says_it_was_already_there(ctx):
    blueprint.apply(ctx, restaurant_bundle(), apps=None)

    again = blueprint.apply(ctx, restaurant_bundle(), apps=None)

    assert again.created == {}
    statuses = {dataset["key"]: dataset["status"] for app in again.report["apps"] for dataset in app["datasets"]}
    assert set(statuses.values()) == {"already"}
    assert call(ctx, "inventory.product.list", limit=1).total == 2
    assert call(ctx, "table.table.list", limit=1).total == 2


def test_a_row_an_app_refuses_fails_alone_and_the_rest_loads(ctx):
    bundle = restaurant_bundle(
        **{
            "inventory.product": [
                {"name": "Croquetas", "sku": "ENT-01", "price": 850, "cost": 0, "stock": "", "low_stock_threshold": "", "unit": "ud", "ean13": "", "description": "", "tax_category_key": "restaurant.food", "categories": ["Entrantes"]},
                {"name": "", "sku": "BAD-01", "price": 100, "cost": 0, "stock": "", "low_stock_threshold": "", "unit": "ud", "ean13": "", "description": "", "tax_category_key": "", "categories": []},
            ]
        }
    )

    result = blueprint.apply(ctx, bundle, apps=None)

    inventory = next(app for app in result.report["apps"] if app["id"] == "inventory")
    products = next(dataset for dataset in inventory["datasets"] if dataset["key"] == "inventory.product")
    assert (products["status"], products["created"], products["failed"]) == ("partial", 1, 1)
    assert products["problems"] and "BAD-01" in products["problems"][0]
    assert inventory["status"] == "partial"
    assert next(app for app in result.report["apps"] if app["id"] == "table")["status"] == "applied"
    assert result.report["status"] == "partial"


def test_a_product_whose_category_is_not_there_is_created_and_the_missing_link_is_told(ctx):
    bundle = restaurant_bundle(
        **{
            "inventory.product": [
                {"name": "Tarta", "sku": "POS-01", "price": 500, "cost": 0, "stock": "", "low_stock_threshold": "", "unit": "ud", "ean13": "", "description": "", "tax_category_key": "restaurant.food", "categories": ["Postres"]},
            ]
        }
    )

    result = blueprint.apply(ctx, bundle, apps=None)

    products = next(
        dataset for app in result.report["apps"] for dataset in app["datasets"] if dataset["key"] == "inventory.product"
    )
    assert (products["status"], products["created"]) == ("partial", 1)
    assert "Postres" in products["problems"][0]


def test_only_the_apps_chosen_load(ctx):
    result = blueprint.apply(ctx, restaurant_bundle(), apps={"table"})

    assert call(ctx, "inventory.product.list", limit=1).total == 0
    assert call(ctx, "table.table.list", limit=1).total == 2
    statuses = {app["id"]: app["status"] for app in result.report["apps"]}
    assert statuses == {"inventory": "not_selected", "table": "applied"}


def test_an_app_this_hub_does_not_know_is_told_and_skipped(ctx):
    bundle = restaurant_bundle()
    bundle.manifest["apps"] = ["inventory", "table", "bakery_oven"]

    result = blueprint.apply(ctx, bundle, apps=None)

    assert {app["id"]: app["status"] for app in result.report["apps"]}["bakery_oven"] == "unknown"


def test_an_app_that_is_not_on_is_told_and_nothing_of_it_loads(ctx, monkeypatch):
    monkeypatch.setattr(blueprint, "active_apps", lambda scope: frozenset({"table"}))

    result = blueprint.apply(ctx, restaurant_bundle(), apps=None)

    assert {app["id"]: app["status"] for app in result.report["apps"]} == {"inventory": "inactive", "table": "applied"}
    assert result.report["status"] == "partial"


def test_a_template_never_brings_personal_data_even_if_its_file_says_so(ctx):
    bundle = restaurant_bundle(**{"customer.customer": [{"name": "Lucía Pérez", "email": "lucia@example.com", "phone": ""}]})
    bundle.manifest["apps"] = ["inventory", "table", "customer"]

    result = blueprint.apply(ctx, bundle, apps=None)

    customers = next(app for app in result.report["apps"] if app["id"] == "customer")["datasets"][0]
    assert customers["status"] == "discarded"
    assert call(ctx, "customer.customer.list", limit=1).total == 0


def test_a_backup_brings_the_customers_back(ctx):
    bundle = blueprint.Bundle(
        manifest=manifest(purpose="backup", apps=["customer"]),
        data={"customer.customer": [{"name": "Lucía Pérez", "email": "lucia@example.com", "phone": "+34600111222", "notes": "Alérgica"}]},
    )

    result = blueprint.apply(ctx, bundle, apps=None)

    [row] = call(ctx, "customer.customer.list", limit=10).rows
    assert (row.name, row.email) == ("Lucía Pérez", "lucia@example.com")
    assert result.created["customer.customer"] == [str(row.id)]


# ── Exporting: the same datasets, read by each app's list (BASE-G101, BASE-G102) ──────────────────────────────────


def test_what_an_export_reads_loads_into_another_business_as_it_was(ctx):
    blueprint.apply(ctx, restaurant_bundle(), apps=None)
    seed = restaurant_bundle()

    exported = blueprint.export_data(ctx, blueprint.selection_of(seed.data), purpose="template")

    for key, rows in seed.data.items():
        assert sorted(exported[key], key=json.dumps) == sorted(rows, key=json.dumps), key


def test_a_template_export_never_reads_personal_data(ctx):
    call(ctx, "customer.customer.create", name="Lucía Pérez", email="lucia@example.com")

    template = blueprint.export_data(ctx, {"customer": ["customer.customer"]}, purpose="template")
    backup = blueprint.export_data(ctx, {"customer": ["customer.customer"]}, purpose="backup")

    assert template == {}
    assert [row["name"] for row in backup["customer.customer"]] == ["Lucía Pérez"]


def test_the_counts_of_every_dataset_of_the_apps_on(ctx):
    blueprint.apply(ctx, restaurant_bundle(), apps=None)

    counts = blueprint.counts(ctx)

    assert {key: counts[key] for key in ("inventory.category", "inventory.product", "table.zone", "table.table")} == {
        "inventory.category": 2,
        "inventory.product": 2,
        "table.zone": 1,
        "table.table": 2,
    }
    assert counts["customer.customer"] == 0


# ── Undoing: exactly the rows a load created (BASE-G108) ───────────────────────────────────────────────────────────


def test_undoing_removes_exactly_what_the_load_created_and_keeps_what_came_after(ctx):
    result = blueprint.apply(ctx, restaurant_bundle(), apps=None)
    mine = call(ctx, "inventory.product.create", name="Mi plato", sku="MIO-01", price=900, tax_category_key="restaurant.food")

    removed = blueprint.undo(ctx, result.created)

    assert [row.sku for row in call(ctx, "inventory.product.list", limit=100).rows] == [mine.sku]
    assert call(ctx, "table.table.list", limit=1).total == 0
    assert call(ctx, "table.zone.list", limit=1).total == 0
    assert {(app["id"], app["removed"]) for app in removed["apps"]} == {("inventory", 4), ("table", 3)}


def test_undoing_what_is_already_gone_counts_it_as_gone(ctx):
    result = blueprint.apply(ctx, restaurant_bundle(), apps=None)
    call(ctx, "table.table.delete", id=result.created["table.table"][0])

    removed = blueprint.undo(ctx, result.created)

    table = next(app for app in removed["apps"] if app["id"] == "table")
    assert (table["removed"], table["failed"]) == (2, 0)


# ── Resetting: every row of the sections chosen (BASE-G109) ────────────────────────────────────────────────────────


def test_the_reset_plan_says_how_many_rows_each_app_would_lose(ctx):
    blueprint.apply(ctx, restaurant_bundle(), apps=None)

    plan = {section["id"]: section for section in blueprint.reset_plan(ctx)}

    assert (plan["inventory"]["rows"], plan["table"]["rows"]) == (4, 3)
    assert plan["inventory"]["label"] == "Inventario"


def test_resetting_a_section_removes_every_row_of_its_app_and_nothing_else(ctx):
    blueprint.apply(ctx, restaurant_bundle(), apps=None)

    report = blueprint.reset(ctx, ["table"])

    assert call(ctx, "table.table.list", limit=1).total == 0
    assert call(ctx, "table.zone.list", limit=1).total == 0
    assert call(ctx, "inventory.product.list", limit=1).total == 2
    assert report["apps"] == [{"id": "table", "label": "Mesas", "removed": 3, "failed": 0, "problems": []}]


def test_an_export_names_its_file_after_the_business_and_its_language():
    assert blueprint.file_name("Bar Pepe / Centro", "es") == "bar-pepe-centro_es.blueprint.zip"
    assert blueprint.file_name("", "en") == "blueprint_en.blueprint.zip"


def test_a_file_in_base64_is_read_as_its_bytes():
    content = a_file()

    assert blueprint.read_base64(base64.b64encode(content).decode()) == blueprint.read_zip(content)
    with pytest.raises(blueprint.BlueprintInvalid) as refused:
        blueprint.read_base64("@@not base64@@")
    assert refused.value.reason == "not_a_blueprint"
