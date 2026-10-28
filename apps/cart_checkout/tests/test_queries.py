"""Read operations of the cart_checkout app: the carts (list and one, with its lines), the lines of a cart
and the orders (list and one).

The cases come from the old module's manifest (search, filters and sort of each list) and its WORKFLOW
(CART_CHECKOUT-F12), with what it got wrong fixed: the carts' search finds a session code too, an active
cart past its expiry reads as expired, and a deleted cart is never listed.
"""

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.cart_checkout.models import Cart
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

from .conftest import NOW, ctx_for, make_cart, make_item, make_order

pytestmark = pytest.mark.django_db

EARLIER = NOW - dt.timedelta(hours=1)
LATER = NOW + dt.timedelta(hours=1)


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


def run(name, data: dict | None = None, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data or {}))


def tokens(page) -> list[str]:
    return [row.session_token for row in page.rows]


def numbers(page) -> list[str]:
    return [row.order_number for row in page.rows]


def at(moment: dt.datetime, **fields) -> Cart:
    """A cart created at ``moment`` (created_at is set by the database on insert)."""
    cart = make_cart(**fields)
    Cart.objects.filter(pk=cart.pk).update(created_at=moment)
    return Cart.objects.get(pk=cart.pk)


@pytest.fixture
def shop():
    """Four live carts and a deleted one, created an hour apart (the newest last)."""
    start = NOW - dt.timedelta(hours=5)
    hour = dt.timedelta(hours=1)
    ana = at(start, session_token="sess_ana", customer_email="ana@example.com", customer_name="Ana García",
             total_items=Decimal("2"), total_amount=2500, notes="VIP")
    bea = at(start + hour, session_token="sess_bea", customer_email="bea@example.com", customer_name="Bea López",
             status="abandoned", total_items=Decimal("1"), total_amount=900, currency="USD")
    old = at(start + 2 * hour, session_token="anon_1", expires_at=EARLIER, total_items=Decimal("0.5"), total_amount=300)
    fresh = at(start + 3 * hour, session_token="anon_2", expires_at=LATER)
    at(start + 4 * hour, session_token="sess_gone", deleted_at=EARLIER)
    return {"ana": ana, "bea": bea, "old": old, "fresh": fresh}


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


# ── Carts ─────────────────────────────────────────────────────────────────────────────────────


def test_the_carts_newest_first_without_the_deleted_ones(shop):
    page = run("cart_checkout.cart.list")
    assert tokens(page) == ["anon_2", "anon_1", "sess_bea", "sess_ana"]
    assert (page.total, page.limit, page.offset) == (4, 50, 0)


def test_an_active_cart_past_its_expiry_reads_as_expired(shop):
    rows = {row.session_token: row.status for row in run("cart_checkout.cart.list").rows}
    assert rows == {"anon_2": "active", "anon_1": "expired", "sess_bea": "abandoned", "sess_ana": "active"}
    assert tokens(run("cart_checkout.cart.list", {"status": "expired"})) == ["anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"status": "active"})) == ["anon_2", "sess_ana"]


def test_a_row_carries_everything_a_cart_says(shop):
    row = run("cart_checkout.cart.list", {"session_token": "sess_ana"}).rows[0]
    assert row.model_dump() == {
        "id": shop["ana"].id,
        "session_token": "sess_ana",
        "customer_email": "ana@example.com",
        "customer_name": "Ana García",
        "status": "active",
        "total_items": Decimal("2.000"),
        "total_amount": 2500,
        "currency": "EUR",
        "currency_decimals": 2,
        "expires_at": None,
        "last_activity_at": None,
        "notes": "VIP",
        "abandon_reason": "",
        "created_by": "",
        "updated_by": "",
        "created_at": shop["ana"].created_at,
        "updated_at": shop["ana"].updated_at,
    }


def test_pages_never_overlap(shop):
    first = run("cart_checkout.cart.list", {"limit": 2})
    second = run("cart_checkout.cart.list", {"limit": 2, "offset": 2})
    assert tokens(first) + tokens(second) == ["anon_2", "anon_1", "sess_bea", "sess_ana"]
    assert first.total == second.total == 4


@pytest.mark.parametrize(
    ("typed", "found"),
    [("SESS_", ["sess_bea", "sess_ana"]), ("bea@", ["sess_bea"]), ("garcía", ["sess_ana"]), ("nobody", [])],
)
def test_the_search_reads_the_code_the_email_and_the_name(shop, typed, found):
    # The old screen said «Search session or email…» but its query never read the session code.
    assert tokens(run("cart_checkout.cart.list", {"search": typed})) == found


def test_the_text_filters_narrow_by_fragment(shop):
    assert tokens(run("cart_checkout.cart.list", {"session_token": "anon"})) == ["anon_2", "anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"customer_email": "EXAMPLE"})) == ["sess_bea", "sess_ana"]
    assert tokens(run("cart_checkout.cart.list", {"customer_name": "lópez"})) == ["sess_bea"]
    assert tokens(run("cart_checkout.cart.list", {"notes": "vip"})) == ["sess_ana"]
    assert tokens(run("cart_checkout.cart.list", {"currency": "usd"})) == ["sess_bea"]


def test_the_ranges_include_both_ends(shop):
    assert tokens(run("cart_checkout.cart.list", {"total_amount_min": 900, "total_amount_max": 2500})) == [
        "sess_bea",
        "sess_ana",
    ]
    assert tokens(run("cart_checkout.cart.list", {"total_items_min": "0.5", "total_items_max": "1"})) == [
        "anon_1",
        "sess_bea",
    ]
    created = shop["bea"].created_at
    assert tokens(run("cart_checkout.cart.list", {"created_from": created, "created_to": created})) == ["sess_bea"]
    assert tokens(run("cart_checkout.cart.list", {"expires_to": NOW})) == ["anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"expires_from": NOW})) == ["anon_2"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("total_amount", ["anon_2", "anon_1", "sess_bea", "sess_ana"]),
        ("-total_amount", ["sess_ana", "sess_bea", "anon_1", "anon_2"]),
        ("session_token", ["anon_1", "anon_2", "sess_ana", "sess_bea"]),
        ("created_at", ["sess_ana", "sess_bea", "anon_1", "anon_2"]),
    ],
)
def test_the_order_of_a_column(shop, sort, expected):
    assert tokens(run("cart_checkout.cart.list", {"sort": sort})) == expected


def test_a_cart_with_its_lines_by_its_code(shop):
    first = make_item(shop["ana"], product_ref="p-1", product_name="Champú")
    second = make_item(shop["ana"], product_ref="p-2", product_name="Tinte", quantity=Decimal("0.5"), unit_price=1200)
    cart = run("cart_checkout.cart.get", {"session_token": "sess_ana"})
    assert (cart.id, cart.status) == (shop["ana"].id, "active")
    assert [item.id for item in cart.items] == [first.id, second.id]
    assert cart.items[1].line_total == 600


def test_a_cart_by_its_customer_or_its_id(shop):
    assert run("cart_checkout.cart.get", {"customer": "Bea@Example.com"}).id == shop["bea"].id
    assert run("cart_checkout.cart.get", {"cart_id": str(shop["old"].id)}).status == "expired"


def test_a_customer_with_several_carts_is_asked_which_one(shop):
    make_cart("sess_ana_2", customer_name="Ana Pérez")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.get", {"customer": "ana"})
    assert caught.value.code == "cart_checkout.cart_ambiguous"


def test_a_customer_with_old_carts_and_one_active_gets_the_active_one(shop):
    # «The cart of Ana» while Ana has a converted cart from last week: the assistant means the live one.
    make_cart("sess_ana_old", customer_email="ana@example.com", status="converted")
    assert run("cart_checkout.cart.get", {"customer": "ana@example.com"}).id == shop["ana"].id


def test_different_customers_matched_by_a_piece_of_the_name_are_asked_which_one(shop):
    # Review (ALTO): «ana» is a piece of «Mariana»; that only one of the two carts is active does not
    # make them the same person, so the active one is never picked for her (a delete, a line or an
    # order would go to someone else).
    Cart.objects.all().delete()
    make_cart("sess_ana", customer_name="Ana García", status="converted")
    make_cart("sess_mariana", customer_name="Mariana Ruiz")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.get", {"customer": "ana"})
    assert caught.value.code == "cart_checkout.cart_ambiguous"
    assert caught.value.message == "“ana” matches several carts: sess_ana, sess_mariana. Say which one."


def test_one_customer_by_name_with_an_old_cart_and_an_active_one_gets_the_active_one(shop):
    # The same full name (whatever the case and the spaces) is one customer: the live cart is meant.
    Cart.objects.all().delete()
    make_cart("sess_old", customer_name="ana  garcía", status="converted")
    active = make_cart("sess_new", customer_name="Ana García")
    assert run("cart_checkout.cart.get", {"customer": "garcía"}).id == active.id


def test_a_deleted_or_unknown_cart_is_not_found(shop):
    for said in ({"session_token": "sess_gone"}, {"session_token": "nope"}):
        with pytest.raises(NotFound) as caught:
            run("cart_checkout.cart.get", said)
        assert caught.value.code == "cart_checkout.cart_not_found"


# ── Lines ─────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def lines(shop):
    cart = shop["ana"]
    return [
        make_item(cart, product_ref="p-1", product_name="Champú", sku="SH-1", quantity=Decimal("2"), unit_price=1250),
        make_item(cart, product_ref="p-2", product_name="Tinte rubio", sku="TI-9", quantity=Decimal("1"), unit_price=900),
        make_item(cart, product_ref="p-3", product_name="Peine", quantity=Decimal("0.5"), unit_price=200),
        make_item(shop["bea"], product_ref="p-1", product_name="Champú"),
    ]


def names(page) -> list[str]:
    return [row.product_name for row in page.rows]


def test_the_lines_of_a_cart_as_they_were_added(lines):
    page = run("cart_checkout.item.list", {"session_token": "sess_ana"})
    assert names(page) == ["Champú", "Tinte rubio", "Peine"]
    assert page.total == 3
    assert names(run("cart_checkout.item.list", {"cart_id": str(lines[3].cart_id)})) == ["Champú"]


def test_the_lines_search_filter_and_sort(lines):
    ana = {"session_token": "sess_ana"}
    assert names(run("cart_checkout.item.list", ana | {"search": "ti-9"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"product_ref": "p-3"})) == ["Peine"]
    assert names(run("cart_checkout.item.list", ana | {"product_name": "TINTE"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"sku": "sh"})) == ["Champú"]
    assert names(run("cart_checkout.item.list", ana | {"quantity_min": "1", "quantity_max": "1"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"unit_price_max": 900})) == ["Tinte rubio", "Peine"]
    assert names(run("cart_checkout.item.list", ana | {"line_total_min": 2500})) == ["Champú"]
    assert names(run("cart_checkout.item.list", ana | {"sort": "-line_total"})) == ["Champú", "Tinte rubio", "Peine"]


def test_the_lines_of_an_unknown_cart_are_not_found(lines):
    with pytest.raises(NotFound):
        run("cart_checkout.item.list", {"session_token": "nope"})


def test_one_line_by_its_id(lines):
    item = run("cart_checkout.item.get", {"item_id": str(lines[1].id)})
    assert (item.product_name, item.unit_price, item.cart_id) == ("Tinte rubio", 900, lines[1].cart_id)
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.get", {"item_id": "0199e2a0-0000-7000-8000-000000000000"})
    assert caught.value.code == "cart_checkout.item_not_found"


def test_the_lines_of_a_deleted_cart_are_gone_with_it(shop):
    # cart_checkout#8 (CART_CHECKOUT-F06): a deleted cart's lines stay in the database for its orders,
    # but nobody reads them any more, neither the cart's list nor one line by its id.
    gone = Cart.objects.get(session_token="sess_gone")
    line = make_item(gone, product_name="Champú")
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.get", {"item_id": str(line.id)})
    assert caught.value.code == "cart_checkout.item_not_found"
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.list", {"cart_id": str(gone.id)})
    assert caught.value.code == "cart_checkout.cart_not_found"


# ── Orders ────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def orders(shop):
    first = make_order(shop["ana"], order_number="OS-20261013-0001", customer_email="ana@example.com",
                       total_amount=2500, payment_method="Card", status="completed",
                       placed_at=NOW - dt.timedelta(days=1), paid_at=NOW - dt.timedelta(days=1))
    second = make_order(shop["bea"], order_number="OS-20261014-0001", customer_email="bea@example.com",
                        total_amount=900, currency="USD", payment_method="Transfer", status="paid",
                        placed_at=EARLIER, paid_at=NOW)
    third = make_order(shop["ana"], order_number="OS-20261014-0002", customer_email="ana@example.com",
                       total_amount=300, shipping_method="Courier", placed_at=NOW)
    return [first, second, third]


def test_the_orders_newest_first(orders):
    page = run("cart_checkout.order.list")
    assert numbers(page) == ["OS-20261014-0002", "OS-20261014-0001", "OS-20261013-0001"]
    assert page.total == 3


def test_an_order_row_says_its_cart_code_and_its_currency(orders):
    row = run("cart_checkout.order.list", {"order_number": "20261014-0001"}).rows[0]
    assert (row.session_token, row.currency, row.total_amount, row.status) == ("sess_bea", "USD", 900, "paid")


@pytest.mark.parametrize(
    ("typed", "found"),
    [("0002", ["OS-20261014-0002"]), ("BEA@", ["OS-20261014-0001"]), ("20261013", ["OS-20261013-0001"])],
)
def test_the_order_search_reads_the_number_and_the_email(orders, typed, found):
    assert numbers(run("cart_checkout.order.list", {"search": typed})) == found


def test_the_order_filters(orders, shop):
    def find(**params):
        return numbers(run("cart_checkout.order.list", params))

    assert find(status="paid") == ["OS-20261014-0001"]
    assert find(cart_id=str(shop["ana"].id)) == ["OS-20261014-0002", "OS-20261013-0001"]
    assert find(customer_email="ana@") == ["OS-20261014-0002", "OS-20261013-0001"]
    assert find(payment_method="trans") == ["OS-20261014-0001"]
    assert find(shipping_method="Courier") == ["OS-20261014-0002"]
    assert find(currency="usd") == ["OS-20261014-0001"]
    assert find(total_amount_min=300, total_amount_max=900) == ["OS-20261014-0002", "OS-20261014-0001"]
    assert find(placed_from=EARLIER, placed_to=NOW) == ["OS-20261014-0002", "OS-20261014-0001"]
    assert find(paid_to=EARLIER) == ["OS-20261013-0001"]


def test_the_orders_sort_by_a_column(orders):
    assert numbers(run("cart_checkout.order.list", {"sort": "total_amount"})) == [
        "OS-20261014-0002",
        "OS-20261014-0001",
        "OS-20261013-0001",
    ]
    assert numbers(run("cart_checkout.order.list", {"sort": "order_number"}))[0] == "OS-20261013-0001"


def test_an_order_by_its_number_or_its_id(orders):
    assert run("cart_checkout.order.get", {"order_number": "os-20261014-0002"}).id == orders[2].id
    whole = run("cart_checkout.order.get", {"order_id": str(orders[0].id)})
    assert (whole.order_number, whole.payment_method, whole.status) == ("OS-20261013-0001", "Card", "completed")
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.order.get", {"order_number": "OS-20991231-0001"})
    assert caught.value.code == "cart_checkout.order_not_found"


# ── Who may look ──────────────────────────────────────────────────────────────────────────────


def test_an_employee_may_look(orders):
    assert run("cart_checkout.cart.list", role="hub_employee").total == 4
    assert run("cart_checkout.order.list", role="hub_employee").total == 3


def test_nobody_without_the_view_permission(orders):
    with pytest.raises(PermissionDenied):
        run("cart_checkout.cart.list", permissions={"cart_checkout.manage_cart"})


# ── The pages filter with the declared filters only ───────────────────────────────────────────

OPERATIONS_TS = Path(__file__).resolve().parents[1] / "frontend" / "operations.d.ts"


def ts_fields(interface: str) -> set[str]:
    """The fields of ``interface`` in the pages' typed operations (``frontend/operations.d.ts``)."""
    source = OPERATIONS_TS.read_text()
    found = re.search(rf"export interface {interface}(?: extends (\w+))? \{{(.*?)\n\}}", source, re.S)
    assert found, f"{interface} is not in operations.d.ts"
    fields = set(re.findall(r"^\s+(\w+)\??:", found.group(2), re.M))
    return fields | (ts_fields(found.group(1)) if found.group(1) else set())


@pytest.mark.parametrize(
    ("interface", "schema"),
    [("CartListIn", CartListIn), ("ItemListIn", ItemListIn), ("OrderListIn", OrderListIn)],
)
def test_the_pages_filter_with_the_declared_filters_only(interface, schema):
    # The old module's filters lived in its manifest; a filter the query does not declare did nothing.
    # The pages build their query as these TypeScript types (vue-tsc checks it); the types are the schema.
    assert ts_fields(interface) == set(schema.model_fields)
