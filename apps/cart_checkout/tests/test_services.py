"""Write operations of the cart_checkout app: carts (create, abandon, delete, clear, expire), their lines
(add, change, remove) and the orders made from them (initiate with their number of the day, mark paid,
fail, complete).

The cases come from the old module's WORKFLOW, its tests and its handler (Rust), with its silent no-ops
turned into refusals: an action on a cart that is not active, a step from the wrong state, or an order
from an empty cart says why, changes nothing, spends no number and records no event
(CART_CHECKOUT-F02 to F11 «parcial»).
"""

import datetime as dt
import json
from decimal import Decimal

import psycopg
import pytest
from django.utils import translation
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter
from base.models import Hub

from .conftest import A, B, NOW, ctx_for, make_cart, make_item, make_order

pytestmark = pytest.mark.django_db

WAIT = 1.0
QUIET = 0.3
LATER = NOW + dt.timedelta(hours=1)
EARLIER = NOW - dt.timedelta(hours=1)


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


def run(name, data: dict, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


def refused(error, code: str):
    """Asserts the operation was refused with ``code`` and left no event."""
    assert error.value.code == code
    assert events() == []


def stored(cart) -> Cart:
    return Cart.objects.get(pk=cart.pk)


def add(cart_or_token, quantity="1", unit_price=1250, **fields):
    token = cart_or_token if isinstance(cart_or_token, str) else cart_or_token.session_token
    data = {
        "session_token": token,
        "product_ref": "p-1",
        "product_name": "Champú",
        "quantity": quantity,
        "unit_price": unit_price,
    } | fields
    return run("cart_checkout.item.add", data)


def initiate(token="sess_1", **fields):
    data = {"session_token": token, "customer_email": "ana@example.com"} | fields
    return run("cart_checkout.checkout.initiate", data)


@pytest.mark.parametrize(
    ("name", "permission"),
    [
        ("cart_checkout.cart.create", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.mark_abandoned", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.delete", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.clear", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.cleanup_expired", "cart_checkout.manage_cart"),
        ("cart_checkout.item.add", "cart_checkout.manage_cart"),
        ("cart_checkout.item.update", "cart_checkout.manage_cart"),
        ("cart_checkout.item.remove", "cart_checkout.manage_cart"),
        ("cart_checkout.checkout.initiate", "cart_checkout.checkout"),
        ("cart_checkout.order.mark_paid", "cart_checkout.checkout"),
        ("cart_checkout.order.fail", "cart_checkout.checkout"),
        ("cart_checkout.order.complete", "cart_checkout.checkout"),
        ("cart_checkout.customer.erase", "cart_checkout.manage_cart"),
    ],
)
def test_declarations(name, permission):
    op = get(name)
    assert (op.kind, op.permission, op.expose_api) == ("command", permission, True)


# ── Create (CART_CHECKOUT-F01) ────────────────────────────────────────────────────────────────


def test_creating_a_cart_in_the_business_currency():
    cart = run(
        "cart_checkout.cart.create",
        {"session_token": "sess_1", "customer_email": "ana@example.com", "customer_name": "Ana García"},
        actor="Ana",
    )
    assert (cart.session_token, cart.status, cart.currency) == ("sess_1", "active", "EUR")
    assert (cart.total_items, cart.total_amount) == (Decimal("0"), 0)
    assert (cart.customer_email, cart.customer_name) == ("ana@example.com", "Ana García")
    row = Cart.objects.get(pk=cart.id)
    assert (row.created_by, row.updated_by, row.last_activity_at) == ("Ana", "Ana", NOW)
    assert events() == ["cart_checkout.cart.created"]
    assert payload("cart_checkout.cart.created") == {
        "id": str(cart.id),
        "session_token": "sess_1",
        "currency": "EUR",
    }


@pytest.mark.parametrize(("currency", "expected"), [("usd", "USD"), (None, "EUR"), ("", "EUR")])
def test_an_explicit_currency_wins_and_an_empty_one_is_the_business_one(currency, expected):
    # The old cart_currency batteries: a cart without a currency is born in the business's one.
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "currency": currency})
    assert cart.currency == expected


def test_a_cart_without_a_currency_takes_the_business_one_never_a_literal_euro():
    # cart_checkout#32, #34: a hub that does not work in euros got euro carts from the screen, the
    # assistant and the API. The cart follows the business's country (test_business_currency.py).
    Hub.objects.filter(slug="a").update(country="GB")
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    assert cart.currency == "GBP"
    assert payload("cart_checkout.cart.created")["currency"] == "GBP"


def test_a_cart_can_carry_its_expiry():
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "expires_at": LATER.isoformat()})
    assert cart.expires_at == LATER


def test_a_session_code_in_use_is_refused_under_its_field():
    make_cart("sess_1")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.create", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.session_taken")
    assert caught.value.fields == {"session_token": "There is already a cart with that session."}
    assert Cart.objects.count() == 1


def test_a_deleted_cart_frees_its_session_code():
    make_cart("sess_1", deleted_at=EARLIER)
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    assert Cart.objects.filter(session_token="sess_1").count() == 2
    assert cart.status == "active"


def test_an_employee_only_looks():
    with pytest.raises(PermissionDenied):
        run("cart_checkout.cart.create", {"session_token": "sess_1"}, role="hub_employee")
    assert Cart.objects.count() == 0


# ── How a cart is named ───────────────────────────────────────────────────────────────────────


def test_a_cart_is_found_by_its_id_its_code_or_its_customer():
    cart = make_cart("sess_1", customer_email="ana@example.com", customer_name="Ana García")
    make_cart("sess_2", customer_email="bea@example.com", customer_name="Bea López")
    for said in (
        {"cart_id": str(cart.id)},
        {"session_token": "sess_1"},
        {"customer": "ANA@example.com"},
        {"customer": "garcía"},
    ):
        result = run("cart_checkout.cart.mark_abandoned", said)
        assert result.id == cart.id, said
        Cart.objects.filter(pk=cart.pk).update(status="active")


def test_a_customer_with_several_carts_asks_which_one():
    make_cart("sess_1", customer_name="Ana García")
    make_cart("sess_2", customer_name="Ana Pérez")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"customer": "ana"})
    refused(caught, "cart_checkout.cart_ambiguous")
    assert caught.value.message == "“ana” matches several carts: sess_1, sess_2. Say which one."


def test_a_cart_that_does_not_exist_or_was_deleted_is_not_found():
    make_cart("gone", deleted_at=EARLIER)
    for said in ({"session_token": "nope"}, {"session_token": "gone"}, {"customer": "nobody"}):
        with pytest.raises(NotFound) as caught:
            run("cart_checkout.cart.mark_abandoned", said)
        assert caught.value.code == "cart_checkout.cart_not_found", said
    assert events() == []


# ── Abandon (CART_CHECKOUT-F05) ───────────────────────────────────────────────────────────────


def test_abandoning_an_active_cart_keeps_its_lines_and_its_reason():
    cart = make_cart("sess_1")
    make_item(cart)
    result = run(
        "cart_checkout.cart.mark_abandoned", {"session_token": "sess_1", "reason": "Left the shop"}, actor="Bea"
    )
    assert (result.status, result.abandon_reason) == ("abandoned", "Left the shop")
    assert stored(cart).updated_by == "Bea"
    assert CartItem.objects.filter(cart=cart).count() == 1
    assert events() == ["cart_checkout.cart.abandoned"]
    assert payload("cart_checkout.cart.abandoned") == {"id": str(cart.id), "session_token": "sess_1"}


@pytest.mark.parametrize("status", ["abandoned", "converted", "expired"])
def test_only_an_active_cart_is_abandoned(status):
    make_cart("sess_1", status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    label = {"abandoned": "Abandoned", "converted": "Converted", "expired": "Expired"}[status]
    assert caught.value.message == f"This cart no longer takes changes: it is {label}."


def test_an_active_cart_past_its_expiry_is_already_expired():
    make_cart("sess_1", expires_at=EARLIER)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    assert caught.value.message == "This cart no longer takes changes: it is Expired."


# ── Delete (CART_CHECKOUT-F06) ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["active", "converted"])
def test_deleting_a_cart_in_any_status_keeps_its_orders(status):
    cart = make_cart("sess_1", status=status)
    order = make_order(cart)
    result = run("cart_checkout.cart.delete", {"session_token": "sess_1"})
    assert result.id == cart.id
    assert stored(cart).deleted_at == NOW
    assert Order.objects.filter(pk=order.pk).exists()
    assert events() == ["cart_checkout.cart.deleted"]
    assert payload("cart_checkout.cart.deleted") == {"id": str(cart.id), "session_token": "sess_1"}
    with pytest.raises(NotFound):
        run("cart_checkout.cart.get", {"cart_id": str(cart.id)})


def test_deleting_a_cart_that_is_gone_is_refused():
    make_cart("sess_1", deleted_at=EARLIER)
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.cart.delete", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_found")


# ── Clear (CART_CHECKOUT-F04) ─────────────────────────────────────────────────────────────────


def test_clearing_a_cart_removes_its_lines_and_zeroes_its_totals():
    make_cart("sess_1")
    add("sess_1", quantity="2")
    add("sess_1", quantity="1", unit_price=500)
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    assert (result.status, result.total_items, result.total_amount) == ("active", Decimal("0"), 0)
    assert CartItem.objects.count() == 0
    assert events() == ["cart_checkout.cart.cleared"]


def test_clearing_an_empty_cart_changes_nothing():
    make_cart("sess_1")
    run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    assert events() == []


def test_only_an_active_cart_is_cleared():
    cart = make_cart("sess_1", status="abandoned")
    make_item(cart)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.count() == 1


# ── Expire (CART_CHECKOUT-F07) ────────────────────────────────────────────────────────────────


def test_expiring_marks_the_overdue_active_carts_and_says_how_many():
    overdue = make_cart("old_1", expires_at=EARLIER)
    make_cart("old_2", expires_at=NOW)  # its expiry is now: expired
    make_cart("future", expires_at=LATER)
    make_cart("forever")
    make_cart("left", status="abandoned", expires_at=EARLIER)
    make_cart("gone", expires_at=EARLIER, deleted_at=EARLIER)
    result = run("cart_checkout.cart.cleanup_expired", {}, actor="*")
    assert result.expired == 2
    assert stored(overdue).status == "expired"
    assert dict(Cart.objects.values_list("session_token", "status")) == {
        "old_1": "expired",
        "old_2": "expired",
        "future": "active",
        "forever": "active",
        "left": "abandoned",
        "gone": "active",
    }
    assert events() == ["cart_checkout.cart.expired"]
    assert payload("cart_checkout.cart.expired") == {"count": 2}


def test_expiring_without_overdue_carts_says_zero_and_records_nothing():
    make_cart("future", expires_at=LATER)
    assert run("cart_checkout.cart.cleanup_expired", {}).expired == 0
    assert events() == []


# ── Lines (CART_CHECKOUT-F02, F03) ────────────────────────────────────────────────────────────


def test_adding_a_line_computes_its_total_and_the_cart_totals():
    cart = make_cart("sess_1")
    result = add("sess_1", quantity="0.5", unit_price=1200, sku="SH-1", variant_attributes={"size": "M"})
    assert result.removed is False
    assert (result.item.quantity, result.item.unit_price, result.item.line_total) == (Decimal("0.5"), 1200, 600)
    assert (result.item.sku, result.item.variant_attributes) == ("SH-1", {"size": "M"})
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("0.5"), 600)
    assert stored(cart).last_activity_at == NOW
    assert events() == ["cart_checkout.item.added"]
    assert payload("cart_checkout.item.added") == {
        "item_id": str(result.item.id),
        "cart_id": str(cart.id),
        "session_token": "sess_1",
        "product_ref": "p-1",
        "quantity": "0.500",
        "line_total": 600,
    }


@pytest.mark.parametrize(
    ("quantity", "price", "total"),
    [("2", 1250, 2500), ("0.333", 100, 33), ("0.005", 100, 1), ("0.015", 100, 2), ("3", 0, 0)],
)
def test_a_line_total_is_rounded_to_the_cent_half_up(quantity, price, total):
    make_cart("sess_1")
    assert add("sess_1", quantity=quantity, unit_price=price).item.line_total == total


def test_the_cart_totals_are_the_sum_of_its_lines():
    make_cart("sess_1")
    add("sess_1", quantity="2", unit_price=1250)
    result = add("sess_1", quantity="0.5", unit_price=999, product_ref="p-2")
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("2.5"), 2500 + 500)


def test_a_line_goes_to_the_cart_of_the_customer_named():
    cart = make_cart("sess_1", customer_email="ana@example.com")
    result = run(
        "cart_checkout.item.add",
        {"customer": "ana@example.com", "product_ref": "p", "product_name": "Tinte", "quantity": "1", "unit_price": 900},
    )
    assert result.cart.id == cart.id


def test_a_line_whose_total_is_above_what_a_cart_holds_is_refused_under_quantity():
    # Review (BAJO): 1 000 000 × 99 999 999 999,99 € overflowed the database's bigint (a 500).
    make_cart("sess_1")
    with pytest.raises(InvalidPayload) as caught:
        add("sess_1", quantity="1000000", unit_price=9999999999999)
    refused(caught, "invalid_field")
    assert caught.value.fields == {"quantity": "The total of this line (quantity × price) is above what a cart can hold."}
    assert CartItem.objects.count() == 0


def test_a_cart_whose_total_would_go_above_what_it_holds_takes_no_more_lines():
    cart = make_cart("sess_1", total_amount=9_999_999_999_000)
    make_item(cart, unit_price=9_999_999_999_000, line_total=9_999_999_999_000)
    with pytest.raises(InvalidPayload) as caught:
        add("sess_1", quantity="1", unit_price=1000)
    refused(caught, "invalid_field")
    assert caught.value.fields == {"quantity": "The cart's total would be above what a cart can hold."}


def test_a_new_quantity_whose_total_is_too_large_is_refused_and_the_line_stays():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=9999999999999).item
    OutboxEvent.objects.all().delete()
    with pytest.raises(InvalidPayload) as caught:
        run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "2"})
    refused(caught, "invalid_field")
    assert set(caught.value.fields) == {"quantity"}
    assert CartItem.objects.get(pk=line.id).quantity == Decimal("1")


@pytest.mark.parametrize("status", ["abandoned", "converted", "expired"])
def test_a_cart_that_is_not_active_takes_no_line(status):
    make_cart("sess_1", status=status)
    with pytest.raises(Conflict) as caught:
        add("sess_1")
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.count() == 0


def test_an_overdue_cart_takes_no_line():
    make_cart("sess_1", expires_at=EARLIER)
    with pytest.raises(Conflict) as caught:
        add("sess_1")
    refused(caught, "cart_checkout.cart_not_active")


def test_a_line_for_a_cart_that_does_not_exist_is_refused():
    with pytest.raises(NotFound) as caught:
        add("nope")
    refused(caught, "cart_checkout.cart_not_found")


def test_changing_a_quantity_uses_the_price_kept_on_the_line():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "2"})
    assert (result.item.quantity, result.item.line_total, result.removed) == (Decimal("2"), 700, False)
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("2"), 700)
    assert events() == ["cart_checkout.item.updated"]
    assert payload("cart_checkout.item.updated") == {
        "item_id": str(line.id),
        "cart_id": str(result.cart.id),
        "quantity": "2.000",
        "removed": False,
    }


def test_a_quantity_of_zero_removes_the_line():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    add("sess_1", quantity="1", unit_price=100, product_ref="p-2")
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "0"})
    assert (result.item, result.removed) == (None, True)
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("1"), 100)
    assert not CartItem.objects.filter(pk=line.id).exists()
    assert events() == ["cart_checkout.item.updated"]
    assert payload("cart_checkout.item.updated")["removed"] is True


def test_removing_a_line_recomputes_the_totals():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.remove", {"item_id": str(line.id)})
    assert (result.item, result.removed, result.cart.total_amount) == (None, True, 0)
    assert events() == ["cart_checkout.item.removed"]
    assert payload("cart_checkout.item.removed") == {"item_id": str(line.id), "cart_id": str(result.cart.id)}


@pytest.mark.parametrize("name", ["cart_checkout.item.update", "cart_checkout.item.remove"])
def test_a_line_that_does_not_exist_is_refused(name):
    data = {"item_id": "0199e2a0-0000-7000-8000-000000000000"}
    if name.endswith("update"):
        data["quantity"] = "1"
    with pytest.raises(NotFound) as caught:
        run(name, data)
    refused(caught, "cart_checkout.item_not_found")


@pytest.mark.parametrize("name", ["cart_checkout.item.update", "cart_checkout.item.remove"])
def test_the_lines_of_a_cart_that_is_not_active_do_not_change(name):
    cart = make_cart("sess_1", status="converted")
    line = make_item(cart, quantity=Decimal("1"), unit_price=100)
    data = {"item_id": str(line.id)}
    if name.endswith("update"):
        data["quantity"] = "3"
    with pytest.raises(Conflict) as caught:
        run(name, data)
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.get(pk=line.pk).quantity == Decimal("1")


# ── Orders: initiate (CART_CHECKOUT-F08) ──────────────────────────────────────────────────────


def test_initiating_an_order_copies_the_cart_total_with_its_number_of_the_day():
    make_cart("sess_1", currency="USD")
    add("sess_1", quantity="2", unit_price=1250)
    OutboxEvent.objects.all().delete()
    order = initiate(
        shipping_address={"line1": "Calle Mayor 1", "city": "Madrid"},
        shipping_method="Courier",
        payment_method="Card",
        notes="Ring twice",
    )
    assert order.order_number == "OS-20261014-0001"
    assert (order.status, order.total_amount, order.currency) == ("initiated", 2500, "USD")
    assert order.customer_email == "ana@example.com"
    # Without a billing address, the shipping one (the old handler's fallback).
    assert order.billing_address == order.shipping_address == {"line1": "Calle Mayor 1", "city": "Madrid"}
    assert (order.shipping_method, order.payment_method, order.notes) == ("Courier", "Card", "Ring twice")
    assert (order.placed_at, order.session_token) == (NOW, "sess_1")
    assert events() == ["cart_checkout.checkout.initiated"]
    assert payload("cart_checkout.checkout.initiated") == {
        "id": str(order.id),
        "order_number": "OS-20261014-0001",
        "cart_id": str(order.cart_id),
        "total_amount": 2500,
        "currency": "USD",
    }


def test_the_numbers_follow_each_other_and_start_again_each_business_day(frozen):
    make_cart("sess_1")
    add("sess_1")
    assert initiate().order_number == "OS-20261014-0001"
    assert initiate().order_number == "OS-20261014-0002"
    # 23:30 UTC on the 14th is already the 15th in Madrid: the business's day, not the server's.
    frozen.at(dt.datetime(2026, 10, 14, 23, 30, tzinfo=dt.UTC))
    assert initiate().order_number == "OS-20261015-0001"


def test_the_cart_stays_active_and_its_order_total_no_longer_changes():
    make_cart("sess_1")
    add("sess_1", quantity="1", unit_price=1000)
    order = initiate()
    add("sess_1", quantity="1", unit_price=500, product_ref="p-2")
    assert Cart.objects.get(session_token="sess_1").status == "active"
    assert Order.objects.get(pk=order.id).total_amount == 1000


def test_the_order_takes_the_cart_email_when_none_is_given():
    make_cart("sess_1", customer_email="bea@example.com")
    add("sess_1")
    order = run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    assert order.customer_email == "bea@example.com"


def test_an_order_without_any_email_is_refused_under_its_field():
    make_cart("sess_1")
    add("sess_1")
    OutboxEvent.objects.all().delete()
    with pytest.raises(InvalidPayload) as caught:
        run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    refused(caught, "invalid_field")
    assert caught.value.fields == {"customer_email": "Say the customer's email: the cart has none."}
    assert Order.objects.count() == 0


def test_an_empty_cart_makes_no_order_and_spends_no_number():
    make_cart("sess_1")
    with pytest.raises(Conflict) as caught:
        initiate()
    refused(caught, "cart_checkout.cart_empty")
    assert caught.value.message == "This cart has no lines: add a product before starting the order."
    assert Order.objects.count() == 0
    assert not OrderCounter.objects.filter(last__gt=0).exists()


@pytest.mark.parametrize(("fields", "error"), [({"status": "abandoned"}, Conflict), ({"expires_at": EARLIER}, Conflict)])
def test_a_cart_that_is_not_active_makes_no_order(fields, error):
    cart = make_cart("sess_1", **fields)
    make_item(cart)
    with pytest.raises(error) as caught:
        initiate()
    refused(caught, "cart_checkout.cart_not_active")
    assert Order.objects.count() == 0


def test_a_refused_order_leaves_no_gap_in_the_numbers():
    make_cart("sess_1")
    add("sess_1")
    make_cart("empty")
    assert initiate().order_number == "OS-20261014-0001"
    with pytest.raises(Conflict):
        initiate("empty")
    assert initiate().order_number == "OS-20261014-0002"


def test_initiating_needs_the_checkout_permission():
    make_cart("sess_1")
    add("sess_1")
    with pytest.raises(PermissionDenied):
        run(
            "cart_checkout.checkout.initiate",
            {"session_token": "sess_1", "customer_email": "a@example.com"},
            permissions={"cart_checkout.view_cart", "cart_checkout.manage_cart"},
        )


# ── Orders: steps (CART_CHECKOUT-F09 to F11) ──────────────────────────────────────────────────


def test_marking_an_order_paid_stamps_the_time(frozen):
    order = make_order(order_number="OS-20261014-0003")
    frozen.at(LATER)
    result = run("cart_checkout.order.mark_paid", {"order_number": "os-20261014-0003"}, actor="Bea")
    assert (result.status, result.paid_at) == ("paid", LATER)
    assert Order.objects.get(pk=order.pk).updated_by == "Bea"
    assert events() == ["cart_checkout.order.paid"]
    assert payload("cart_checkout.order.paid") == {
        "id": str(order.id),
        "order_number": "OS-20261014-0003",
        "status": "paid",
        "total_amount": 2500,
        "currency": "EUR",
    }


@pytest.mark.parametrize("status", ["paid", "failed", "completed"])
def test_only_an_initiated_order_is_marked_paid(status):
    order = make_order(status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.mark_paid", {"order_id": str(order.id)})
    refused(caught, "cart_checkout.invalid_transition")
    label = {"paid": "Paid", "failed": "Failed", "completed": "Completed"}[status]
    assert caught.value.message == f"Only an initiated order can be marked as paid; this one is {label}."


@pytest.mark.parametrize("status", ["initiated", "paid"])
def test_failing_an_order_keeps_its_reason(status):
    order = make_order(status=status)
    result = run("cart_checkout.order.fail", {"order_id": str(order.id), "reason": "Card declined"})
    assert (result.status, result.failure_reason, result.failed_at) == ("failed", "Card declined", NOW)
    assert Cart.objects.get(pk=order.cart_id).status == "active"
    assert events() == ["cart_checkout.order.failed"]


@pytest.mark.parametrize("status", ["failed", "completed"])
def test_a_completed_or_failed_order_cannot_fail(status):
    order = make_order(status=status, failure_reason="first")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.fail", {"order_id": str(order.id), "reason": "again"})
    refused(caught, "cart_checkout.invalid_transition")
    assert Order.objects.get(pk=order.pk).failure_reason == "first"


def test_completing_a_paid_order_converts_its_cart():
    order = make_order(status="paid")
    result = run("cart_checkout.order.complete", {"order_id": str(order.id)})
    assert (result.status, result.completed_at) == ("completed", NOW)
    assert Cart.objects.get(pk=order.cart_id).status == "converted"
    assert events() == ["cart_checkout.order.completed"]


def test_completing_an_order_whose_cart_was_deleted_leaves_the_cart_alone():
    order = make_order(make_cart("gone", deleted_at=EARLIER), status="paid")
    assert run("cart_checkout.order.complete", {"order_id": str(order.id)}).status == "completed"
    assert Cart.objects.get(pk=order.cart_id).status == "active"


@pytest.mark.parametrize("status", ["initiated", "failed", "completed"])
def test_only_a_paid_order_is_completed(status):
    order = make_order(status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.complete", {"order_id": str(order.id)})
    refused(caught, "cart_checkout.invalid_transition")
    assert Cart.objects.get(pk=order.cart_id).status == "active"


def test_an_order_that_does_not_exist_is_refused():
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.order.mark_paid", {"order_number": "OS-20991231-0001"})
    refused(caught, "cart_checkout.order_not_found")


def test_an_employee_cannot_mark_an_order_paid():
    order = make_order()
    with pytest.raises(PermissionDenied):
        run("cart_checkout.order.mark_paid", {"order_id": str(order.id)}, role="hub_employee")
    assert Order.objects.get(pk=order.pk).status == "initiated"


def test_the_refusals_speak_spanish():
    make_cart("sess_1", status="abandoned")
    with translation.override("es"), pytest.raises(Conflict) as caught:
        add("sess_1")
    assert caught.value.message == "Este carrito ya no admite cambios: está Abandonado."


# ── Personal data (CART_CHECKOUT-F14) ─────────────────────────────────────────────────────────


@pytest.fixture
def ana_and_bea():
    """Ana's carts (one live, one deleted) and orders, and Bea's, which must stay as they are."""
    live = make_cart(
        "sess_ana", customer_email="ana@example.com", customer_name="Ana García", notes="Call her", abandon_reason="x"
    )
    gone = make_cart("sess_ana_old", customer_email="ANA@example.com", customer_name="Ana", deleted_at=EARLIER)
    personal = {
        "shipping_address": {"line1": "Calle Mayor 1"},
        "billing_address": {"line1": "Calle Mayor 1"},
        "notes": "Leave it at the door",
        "failure_reason": "Card of Ana declined",
    }
    by_email = make_order(make_cart("sess_other", customer_email="other@example.com"), customer_email="ana@example.com", **personal)
    by_cart = make_order(live, order_number="OS-20261014-0002", customer_email="ana.work@example.com", **personal)
    bea = make_cart("sess_bea", customer_email="bea@example.com", customer_name="Bea", notes="Keep")
    bea_order = make_order(bea, order_number="OS-20261014-0003", customer_email="bea@example.com", notes="Keep")
    return {"live": live, "gone": gone, "by_email": by_email, "by_cart": by_cart, "bea": bea, "bea_order": bea_order}


def test_erasing_a_customer_empties_their_personal_data_in_carts_and_orders(ana_and_bea):
    result = run("cart_checkout.customer.erase", {"email": "Ana@Example.com"}, actor="Bea")
    assert (result.carts, result.orders) == (2, 2)
    for cart in (ana_and_bea["live"], ana_and_bea["gone"]):
        row = Cart.objects.get(pk=cart.pk)
        assert (row.customer_email, row.customer_name, row.notes, row.abandon_reason) == ("", "", "", ""), cart
    for order in (ana_and_bea["by_email"], ana_and_bea["by_cart"]):
        row = Order.objects.get(pk=order.pk)
        assert (row.customer_email, row.shipping_address, row.billing_address, row.notes, row.failure_reason) == (
            "",
            {},
            {},
            "",
            "",
        ), order
    # The orders' numbers, totals and statuses stay: they are not personal data.
    assert Order.objects.get(pk=ana_and_bea["by_cart"].pk).total_amount == 2500
    # Nobody else is touched.
    bea = Cart.objects.get(pk=ana_and_bea["bea"].pk)
    assert (bea.customer_email, bea.customer_name, bea.notes) == ("bea@example.com", "Bea", "Keep")
    assert Order.objects.get(pk=ana_and_bea["bea_order"].pk).notes == "Keep"
    assert Cart.objects.get(pk=ana_and_bea["live"].pk).updated_by == "Bea"
    # The event says how many, never whose.
    assert events() == ["cart_checkout.customer.erased"]
    assert payload("cart_checkout.customer.erased") == {"carts": 2, "orders": 2}


def test_erasing_an_email_nobody_has_changes_nothing(ana_and_bea):
    result = run("cart_checkout.customer.erase", {"email": "nobody@example.com"})
    assert (result.carts, result.orders) == (0, 0)
    assert events() == []


def test_erasing_needs_the_manage_permission(ana_and_bea):
    with pytest.raises(PermissionDenied):
        run("cart_checkout.customer.erase", {"email": "ana@example.com"}, role="hub_employee")
    assert Cart.objects.get(pk=ana_and_bea["live"].pk).customer_email == "ana@example.com"


# ── The whole flow, as the old module's screens and assistant run it ─────────────────────────


def test_from_a_new_cart_to_a_completed_order():
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "customer_email": "ana@example.com"})
    add("sess_1", quantity="2", unit_price=1250)
    order = run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    run("cart_checkout.order.mark_paid", {"order_number": order.order_number})
    run("cart_checkout.order.complete", {"order_number": order.order_number})
    assert Cart.objects.get(pk=cart.id).status == "converted"
    assert Order.objects.get(pk=order.id).status == "completed"
    assert events() == [
        "cart_checkout.cart.created",
        "cart_checkout.item.added",
        "cart_checkout.checkout.initiated",
        "cart_checkout.order.paid",
        "cart_checkout.order.completed",
    ]


# ── Notifications: after the COMMIT, on the channel of the command's scope only ───────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_cart_created_in_b_notifies_the_channel_of_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    run("cart_checkout.cart.create", {"session_token": "sess_b"}, scope=B)
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["cart_checkout.cart.created"]})]
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_step_notifies_nobody(listen):
    order = make_order(status="completed")
    on_a, on_b = listen(A), listen(B)
    with pytest.raises(Conflict):
        run("cart_checkout.order.mark_paid", {"order_id": str(order.id)}, scope=B)
    assert received(on_b, timeout=QUIET) == []
    assert received(on_a, timeout=QUIET) == []
