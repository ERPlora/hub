"""Read operations of the cart_checkout app: the carts (list and one, with its lines), the lines of a cart
and the orders (list and one).

The cases come from the old module's manifest (search, filters and sort of each list) and its WORKFLOW
(CART_CHECKOUT-F12), with what it got wrong fixed: the carts' search finds a session code too, an active
cart past its expiry reads as expired, and a deleted cart is never listed.

Each module of queries/ has its cases in test_queries_<module>.py; here, what every operation declares, who may look,
the typed operations the pages build their queries with and the ties of every list.
"""

from pathlib import Path

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.cart_checkout.models import Cart, CartItem, Order
from apps.cart_checkout.schemas import (
    CartDetailOut,
    CartListIn,
    CartPage,
    CartRefIn,
    ItemListIn,
    ItemOut,
    ItemPage,
    ItemRefIn,
    OrderListIn,
    OrderOut,
    OrderPage,
    OrderRefIn,
)

from base.tests.ordering import assert_reads_backwards, listed_with
from base.tests.typed_operations import ts_fields

from .conftest import HUB_DB, NOW, make_cart, make_item, make_order, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


@pytest.mark.parametrize(
    ("name", "input", "output"),
    [
        ("cart_checkout.cart.list", CartListIn, CartPage),
        ("cart_checkout.cart.get", CartRefIn, CartDetailOut),
        ("cart_checkout.item.list", ItemListIn, ItemPage),
        ("cart_checkout.item.get", ItemRefIn, ItemOut),
        ("cart_checkout.order.list", OrderListIn, OrderPage),
        ("cart_checkout.order.get", OrderRefIn, OrderOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.input, op.output, op.permission, op.expose_api) == (
        "query",
        input,
        output,
        "cart_checkout.view_cart",
        True,
    )


# ── Who may look ──────────────────────────────────────────────────────────────────────────────


def test_an_employee_may_look(orders):
    assert run("cart_checkout.cart.list", role="hub_employee").total == 4
    assert run("cart_checkout.order.list", role="hub_employee").total == 3


def test_nobody_without_the_view_permission(orders):
    with pytest.raises(PermissionDenied):
        run("cart_checkout.cart.list", permissions={"cart_checkout.manage_cart"})


# ── The typed operations declare the schema fields ─────────────────────────────────────────────

OPERATIONS_TS = Path(__file__).resolve().parents[1] / "frontend" / "operations.ts"


@pytest.mark.parametrize(
    ("interface", "schema"),
    [("CartListIn", CartListIn), ("ItemListIn", ItemListIn), ("OrderListIn", OrderListIn)],
)
def test_the_pages_filter_with_the_declared_filters_only(interface, schema):
    # The old module's filters lived in its manifest; a filter the query does not declare did nothing.
    # The pages build their query as these TypeScript types (vue-tsc checks it); the types are the schema.
    assert ts_fields(interface, OPERATIONS_TS) == set(schema.model_fields)


def test_the_typed_outputs_declare_their_schema_fields():
    # The pages read what the server answers through these TypeScript types: a field the schema answers and the
    # type does not declare is invisible to them, as a line's currency was (hub#942).
    assert ts_fields("ItemOut", OPERATIONS_TS) == set(ItemOut.model_fields)


def _tied_carts():
    ids = sorted(make_cart(f"sess_{n}", customer_email="ana@example.com").id for n in range(4))
    Cart.objects.update(created_at=NOW)
    return ids, {}


def _tied_items():
    cart = make_cart()
    ids = sorted(make_item(cart, product_ref=f"p-{n}").id for n in range(4))
    CartItem.objects.update(created_at=NOW)
    return ids, {"cart_id": str(cart.id)}


def _tied_orders():
    ids = sorted(make_order(make_cart(f"sess_{n}"), order_number=f"OS-20261014-000{n}").id for n in range(4))
    Order.objects.update(created_at=NOW)
    return ids, {}


@pytest.mark.parametrize(
    ("operation", "tied", "column"),
    [
        ("cart_checkout.cart.list", _tied_carts, "customer_email"),
        ("cart_checkout.item.list", _tied_items, "unit_price"),
        ("cart_checkout.order.list", _tied_orders, "customer_email"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, tied, column):
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    ids, filters = tied()
    assert_reads_backwards(listed_with(run, operation, column, **filters), ids)
