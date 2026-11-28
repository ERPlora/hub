"""The stock ledger (``apps/inventory/queries/movements.py``): every movement with the product it moved, its
filters, its search and who may read it."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.inventory.models import SaleStock, StockMovement
from apps.inventory.schemas.movements import MovementListIn

from .conftest import HUB_DB, ctx_with, movement, product, run

pytestmark = HUB_DB


def test_the_ledger_most_recent_first_with_the_product_it_moved():
    coffee = product("Coffee", "CAF")
    first = movement(coffee, "initial", 10, 10)
    second = movement(
        coffee, "reception", 5, 15, reference="ALB-7", unit_cost=180, actor="ana"
    )

    page = run("inventory.movement.list", MovementListIn(), role="hub_manager")

    assert [row.id for row in page.rows] == [second.id, first.id]
    assert page.rows[0].model_dump(exclude={"created_at"}) == {
        "id": second.id,
        "product_id": coffee.id,
        "product_name": "Coffee",
        "sku": "CAF",
        "movement_type": "reception",
        "qty": Decimal("5.000"),
        "stock_after": Decimal("15.000"),
        "reason": "",
        "reference": "ALB-7",
        "reference_label": "ALB-7",
        "unit_cost": 180,
        "actor": "ana",
    }


def test_inventory_f16_a_sale_reads_as_the_number_on_its_paper_and_that_number_finds_it_and_its_void():
    # The reference of a sale is its id; the screen shows, and the search finds, its ticket or invoice number (or, with
    # no fiscal document, the sale's own number).
    tea, cake = product("Tea", "TEA"), product("Cake", "CAK")
    ticketed, numbered, unknown = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    SaleStock.objects.create(
        sale_id=ticketed, state="voided", sale_number="20261021-0003", document_number="TICKET-2026-000007"
    )
    SaleStock.objects.create(sale_id=numbered, state="moved", sale_number="20261021-0004")
    movement(tea, "sale", -2, 8, reference=str(ticketed))
    movement(tea, "void", 2, 10, reference=str(ticketed))
    movement(cake, "refund", 1, 4, reference=str(numbered))
    movement(cake, "sale", -1, 3, reference=str(unknown))
    movement(cake, "reception", 5, 8, reference="ALB-7")

    def listed(**filters):
        return [
            (row.product_name, row.movement_type, row.reference_label)
            for row in run("inventory.movement.list", MovementListIn(**filters), role="hub_employee").rows
        ]

    assert listed() == [
        ("Cake", "reception", "ALB-7"),
        ("Cake", "sale", ""),
        ("Cake", "refund", "20261021-0004"),
        ("Tea", "void", "TICKET-2026-000007"),
        ("Tea", "sale", "TICKET-2026-000007"),
    ]
    assert listed(search="ticket-2026-000007") == [
        ("Tea", "void", "TICKET-2026-000007"),
        ("Tea", "sale", "TICKET-2026-000007"),
    ]
    # The sale's own number finds it too, also once it has a ticket.
    assert listed(search="20261021-0003") == listed(search="000007")
    assert listed(search="20261021-0004") == [("Cake", "refund", "20261021-0004")]
    assert listed(reference="000007") == listed(search="000007")
    # A sale's id is still a reference: what it was always searched by.
    assert listed(reference=str(unknown)) == [("Cake", "sale", "")]


def test_a_deleted_product_keeps_its_movements_with_its_name():
    gone = product("Gone", is_deleted=True, is_active=False)
    movement(gone, "initial", 1, 1)
    assert [
        row.product_name
        for row in run("inventory.movement.list", MovementListIn()).rows
    ] == ["Gone"]


def test_the_ledger_filters_and_searches():
    coffee, tea = product("Coffee", "CAF"), product("Tea", "TEA")
    movement(coffee, "reception", 5, 5)
    movement(coffee, "count", -1, 4, reason="broken cup")
    sale = movement(
        tea, "sale", -2, 8, reference="0199a6c0-0000-7000-8000-00000000abcd"
    )

    def listed(**filters):
        return [
            (row.product_name, row.movement_type)
            for row in run("inventory.movement.list", MovementListIn(**filters)).rows
        ]

    assert listed(movement_type="count") == [("Coffee", "count")]
    assert listed(product_id=tea.id) == [("Tea", "sale")]
    assert listed(search="caf") == [("Coffee", "count"), ("Coffee", "reception")]
    assert listed(search="abcd") == [("Tea", "sale")]
    assert listed(reference=sale.reference[-4:]) == [("Tea", "sale")]
    assert [
        row.qty
        for row in run("inventory.movement.list", MovementListIn(sort="qty")).rows
    ] == [
        Decimal("-2.000"),
        Decimal("-1.000"),
        Decimal("5.000"),
    ]


def test_an_employee_reads_the_ledger_and_a_product_editor_without_stock_rights_does_not():
    assert (
        run("inventory.movement.list", MovementListIn(), role="hub_employee").total == 0
    )
    with pytest.raises(PermissionDenied):
        get("inventory.movement.list")(
            ctx_with("inventory.view_product", "inventory.change_product"),
            MovementListIn(),
        )


def test_movements_by_dates_and_ordered_by_type():
    coffee = product("Coffee")
    early = movement(coffee, "reception", 5, 5)
    late = movement(coffee, "count", -1, 4)
    StockMovement.objects.filter(pk=early.pk).update(created_at=datetime(2026, 10, 1, tzinfo=UTC))
    StockMovement.objects.filter(pk=late.pk).update(created_at=datetime(2026, 10, 10, tzinfo=UTC))

    def listed(**params):
        return [row.id for row in run("inventory.movement.list", MovementListIn(**params)).rows]

    assert listed(created_from=datetime(2026, 10, 5, tzinfo=UTC)) == [late.id]
    assert listed(created_to=datetime(2026, 10, 5, tzinfo=UTC)) == [early.id]
    assert listed(sort="movement_type") == [late.id, early.id]  # count < reception
