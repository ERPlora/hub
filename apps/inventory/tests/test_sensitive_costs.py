"""What a product costs reaches only whoever sees the costs (``base.view_costs``): the owner, an administrator and a
manager; never an employee (BASE-F119, INVENTORY-F01, F02, F11 and F17).

An employee reads the catalog, its movements and the stock's figures with the cost empty, by the route and by the
assistant; the Home does not offer them «Stock value (at cost)» (``test_integration_home``). Whoever does not see the
costs cannot write one either: a product or a receipt that carries a cost is refused as an operation they may not run,
and the export leaves its «Cost» column out.
"""

import json
from decimal import Decimal

import pytest
from live import assistant as shared
from live.errors import PermissionDenied
from live.operations import get as operation

from apps.flow.tests.test_api import get
from apps.inventory.models import Product
from apps.inventory.schemas.imports import ProductImportIn
from apps.inventory.schemas.products import ProductFiltersIn, ProductIn, ProductPatchIn
from apps.inventory.schemas.stock import ReceiveIn
from apps.inventory.tests.test_queries import read_csv
from apps.tax.models import TaxCategory
from base.sensitive import VIEW_COSTS

from .conftest import A, HUB_DB, ctx_for, ctx_with

pytestmark = HUB_DB

TAX = "test.general"


@pytest.fixture
def coffee(db):
    TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
    data = ProductIn(name="Coffee", sku="COF", price=180, cost=150, tax_category_key=TAX, initial_stock="3")
    created = operation("inventory.product.create")(ctx_for(), data)
    operation("inventory.stock.receive")(ctx_for(), ReceiveIn(items=[{"product": "COF", "qty": "2", "unit_cost": 160}]))
    return created


@pytest.fixture
def as_role(client, make_user):
    def login(role: str):
        client.force_login(make_user(role, host=A.key, role=role))
        return client

    return login


def run(name: str, data, ctx):
    return operation(name)(ctx, data)


# ── What an employee reads ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("role", "cost"), [("hub_employee", None), ("hub_manager", 160)])
def test_the_product_list_and_its_detail_carry_the_cost_only_to_who_sees_the_costs(coffee, as_role, role, cost):
    client = as_role(role)
    listed = get(client, "/inventory/products")
    detail = get(client, "/inventory/products/detail", id=str(coffee.id))
    for_sale = get(client, "/inventory/products/for_sale")
    assert [response.status_code for response in (listed, detail, for_sale)] == [200, 200, 200]
    assert [row["cost"] for row in listed.json()["rows"]] == [cost]
    assert detail.json()["cost"] == cost
    assert [row["cost"] for row in for_sale.json()["rows"]] == [cost]


@pytest.mark.parametrize(("role", "unit_cost"), [("hub_employee", None), ("hub_manager", 160)])
def test_a_receipt_s_unit_cost_reaches_only_who_sees_the_costs(coffee, as_role, role, unit_cost):
    rows = get(as_role(role), "/inventory/movements").json()["rows"]
    assert [row["unit_cost"] for row in rows if row["movement_type"] == "reception"] == [unit_cost]


@pytest.mark.parametrize(("role", "value"), [("hub_employee", None), ("hub_manager", 5 * 160)])
def test_the_stock_value_reaches_only_who_sees_the_costs_and_the_counts_reach_everyone(coffee, as_role, role, value):
    summary = get(as_role(role), "/inventory/stock/summary").json()
    assert (summary["stock_value"], summary["products_in_stock"]) == (value, 1)


@pytest.mark.parametrize(("role", "cost"), [("hub_employee", None), ("hub_manager", 160)])
def test_the_assistant_answers_the_cost_only_to_who_sees_the_costs(coffee, role, cost):
    outcome = shared.run_tool(ctx_for(role), operation("inventory.product.get"), json.dumps({"product": "COF"}))
    assert outcome.outcome == "ok", outcome.content
    assert json.loads(outcome.content)["cost"] == cost


# ── What whoever does not see the costs may write ──────────────────────────────────────────────────────────────────

ADD = ("inventory.add_product", "inventory.view_product")


def test_a_new_product_with_a_cost_is_refused_to_who_does_not_see_the_costs_and_nothing_is_saved(coffee):
    data = ProductIn(name="Tea", sku="TEA", price=150, cost=90, tax_category_key=TAX)
    with pytest.raises(PermissionDenied):
        run("inventory.product.create", data, ctx_with(*ADD))
    assert not Product.objects.filter(sku="TEA").exists()


def test_without_a_cost_they_add_it_and_it_costs_nothing(coffee):
    run("inventory.product.create", ProductIn(name="Tea", sku="TEA", price=150, tax_category_key=TAX), ctx_with(*ADD))
    assert Product.objects.get(sku="TEA").cost == 0


def test_with_the_costs_the_new_product_keeps_its_cost(coffee):
    data = ProductIn(name="Tea", sku="TEA", price=150, cost=90, tax_category_key=TAX)
    run("inventory.product.create", data, ctx_with(*ADD, VIEW_COSTS))
    assert Product.objects.get(sku="TEA").cost == 90


def test_changing_the_cost_is_refused_to_who_does_not_see_the_costs_and_the_rest_of_an_edit_is_not(coffee):
    editor = ctx_with("inventory.change_product", "inventory.view_product")
    with pytest.raises(PermissionDenied):
        run("inventory.product.update", ProductPatchIn(product="COF", cost=10), editor)
    run("inventory.product.update", ProductPatchIn(product="COF", price=200), editor)
    assert (Product.objects.get(sku="COF").price, Product.objects.get(sku="COF").cost) == (200, 160)


def test_a_receipt_with_a_unit_cost_is_refused_to_who_does_not_see_the_costs_and_one_without_keeps_the_cost(coffee):
    mover = ctx_with("inventory.adjust_stock", "inventory.view_product")
    with pytest.raises(PermissionDenied):
        run("inventory.stock.receive", ReceiveIn(items=[{"product": "COF", "qty": "1", "unit_cost": 10}]), mover)
    run("inventory.stock.receive", ReceiveIn(items=[{"product": "COF", "qty": "1"}]), mover)
    kept = Product.objects.get(sku="COF")
    assert (kept.stock, kept.cost) == (Decimal("6"), 160)


def test_an_import_with_costs_is_refused_whole_to_who_does_not_see_them_and_one_without_goes_in(coffee):
    importer = ctx_with("inventory.import_product", "inventory.add_product")
    row = {"line": 2, "name": "Tea", "sku": "TEA", "price": "1.50", "tax_category_key": TAX}
    with pytest.raises(PermissionDenied):
        run("inventory.product.bulk_create", ProductImportIn(rows=[{**row, "cost": "0.90"}]), importer)
    assert not Product.objects.filter(sku="TEA").exists()
    assert run("inventory.product.bulk_create", ProductImportIn(rows=[row]), importer).created == 1


# ── The export ─────────────────────────────────────────────────────────────────────────────────────────────────────

EXPORT = "inventory.export_product"


def test_the_export_leaves_the_cost_column_out_for_who_does_not_see_the_costs(coffee):
    header, row = read_csv(run("inventory.product.export", ProductFiltersIn(), ctx_with(EXPORT)), ",")
    assert "Cost" not in header
    assert (len(row), row[:3]) == (len(header), ["Coffee", "COF", "€1.80"])


def test_with_the_costs_it_carries_it_beside_the_price(coffee):
    header, row = read_csv(run("inventory.product.export", ProductFiltersIn(), ctx_with(EXPORT, VIEW_COSTS)), ",")
    assert header[:5] == ["Name", "SKU", "Price", "Cost", "Stock"]
    assert row[:5] == ["Coffee", "COF", "€1.80", "€1.60", "5"]

