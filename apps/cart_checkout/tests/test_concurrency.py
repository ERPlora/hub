"""Several people at once on the same day, the same cart, the same order or the same session code: real
sessions in threads, real row locks (WORKBOOK «Cómo está hecho»).

The old module numbered orders with an upsert and a subquery and left holes on refusals; here the
counter's row is raised with ``UPDATE … RETURNING`` in each order's transaction. Whoever comes first wins
a step; the other one waits for it and is refused with the real reason. A cart's totals always equal the
sum of its lines.
"""

import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.db import connection
from django.db.models import Sum
from django.utils import timezone
from live.errors import OperationError
from live.operations import get

from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter

from .conftest import ctx_for, make_cart, make_item, make_order

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list[str]:
    """``ok`` per success, the domain code per refusal, the class name per unexpected failure (an
    ``IntegrityError`` from a repeated number is not «ok»)."""
    return sorted(
        result.code
        if isinstance(result, OperationError)
        else type(result).__name__
        if isinstance(result, Exception)
        else "ok"
        for result in results
    )


def test_ten_orders_at_once_never_repeat_nor_skip_a_number():
    # One cart per order (the cart's lock must not be what queues them) and the day's counter already
    # there (its creation must not be what queues them either): only the counter's own row lock keeps
    # two numbers apart. A read-add-save counter fails this test.
    OrderCounter.objects.create(day=timezone.localdate())
    carts = []
    for n in range(10):
        cart = make_cart(f"sess_{n}", customer_email="ana@example.com", total_amount=100)
        make_item(cart, unit_price=100)
        carts.append(cart)

    def initiate(cart):
        return lambda: run("cart_checkout.checkout.initiate", {"cart_id": str(cart.id)})

    results = at_once(*[initiate(cart) for cart in carts])
    assert codes(results) == ["ok"] * 10
    numbers = sorted(int(result.order_number.rsplit("-", 1)[1]) for result in results)
    assert numbers == list(range(1, 11))
    assert Order.objects.count() == 10


def test_the_first_orders_of_a_day_at_once_create_its_counter_once_and_never_repeat_a_number():
    # Review (BAJO): no counter row yet. Every order inserts the day's row with ON CONFLICT DO NOTHING
    # (the first one wins, the rest wait for its COMMIT and skip) and then raises it with UPDATE …
    # RETURNING: one row for the day, numbers 1 to 10, no IntegrityError.
    assert not OrderCounter.objects.exists()
    carts = []
    for n in range(10):
        cart = make_cart(f"sess_first_{n}", customer_email="ana@example.com", total_amount=100)
        make_item(cart, unit_price=100)
        carts.append(cart)

    def initiate(cart):
        return lambda: run("cart_checkout.checkout.initiate", {"cart_id": str(cart.id)})

    results = at_once(*[initiate(cart) for cart in carts])
    assert codes(results) == ["ok"] * 10
    assert sorted(int(result.order_number.rsplit("-", 1)[1]) for result in results) == list(range(1, 11))
    assert list(OrderCounter.objects.values_list("day", "last")) == [(timezone.localdate(), 10)]


def test_an_order_waits_for_the_day_counter_another_one_is_creating_and_takes_the_next_number(db_dsn):
    # Deterministic: another session has inserted the day's counter row (its first order, number 1) and
    # not committed yet. This order's INSERT … ON CONFLICT DO NOTHING waits for that COMMIT, skips, and its
    # UPDATE … RETURNING gives 2. A check-then-create counter would see no row, insert, and fail with an
    # IntegrityError once the other session commits.
    cart = make_cart("sess_wait", customer_email="ana@example.com", total_amount=100)
    make_item(cart, unit_price=100)
    other = psycopg.connect(db_dsn)
    try:
        other.execute(
            "INSERT INTO cart_checkout_ordercounter (id, day, last) VALUES (%s, %s, 1)",
            (uuid.uuid7(), timezone.localdate()),
        )
        result: list = []
        worker = threading.Thread(
            target=lambda: result.extend(
                at_once(lambda: run("cart_checkout.checkout.initiate", {"cart_id": str(cart.id)}))
            )
        )
        worker.start()
        watcher = psycopg.connect(db_dsn, autocommit=True)
        try:
            for _ in range(200):  # until the order is waiting on the other session's row (≤ 10 s)
                waiting = watcher.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock'"
                ).fetchone()[0]
                if waiting:
                    break
                watcher.execute("SELECT pg_sleep(0.05)")
            assert waiting, "the order did not wait for the other session's counter row"
        finally:
            watcher.close()
        other.commit()
        worker.join(30)
    finally:
        other.close()
    assert codes(result) == ["ok"]
    assert result[0].order_number.endswith("-0002")
    assert OrderCounter.objects.get(day=timezone.localdate()).last == 2


def test_two_marks_as_paid_at_once_one_wins_and_the_other_hears_why():
    order = make_order()
    pay = lambda: run("cart_checkout.order.mark_paid", {"order_id": str(order.id)})  # noqa: E731
    assert codes(at_once(pay, pay)) == ["cart_checkout.invalid_transition", "ok"]


def test_completing_and_failing_at_once_never_leave_both():
    order = make_order(status="paid")
    results = at_once(
        lambda: run("cart_checkout.order.complete", {"order_id": str(order.id)}),
        lambda: run("cart_checkout.order.fail", {"order_id": str(order.id), "reason": "late"}),
    )
    assert codes(results) == ["cart_checkout.invalid_transition", "ok"]
    final = Order.objects.get(pk=order.pk)
    cart = Cart.objects.get(pk=order.cart_id)
    if final.status == "completed":
        assert (final.failure_reason, cart.status) == ("", "converted")
    else:
        assert (final.status, cart.status) == ("failed", "active")


def test_two_carts_with_one_session_code_at_once():
    create = lambda: run("cart_checkout.cart.create", {"session_token": "sess_twin"})  # noqa: E731
    assert codes(at_once(create, create)) == ["cart_checkout.session_taken", "ok"]
    assert Cart.objects.count() == 1


def test_lines_added_at_once_keep_the_totals_equal_to_the_lines():
    cart = make_cart("sess_busy")

    def add(n):
        return lambda: run(
            "cart_checkout.item.add",
            {"session_token": "sess_busy", "product_ref": f"p-{n}", "product_name": "x", "quantity": "1", "unit_price": 100},
        )

    assert codes(at_once(*[add(n) for n in range(6)])) == ["ok"] * 6
    cart.refresh_from_db()
    sums = CartItem.objects.filter(cart=cart).aggregate(items=Sum("quantity"), amount=Sum("line_total"))
    assert (cart.total_items, cart.total_amount) == (sums["items"], sums["amount"]) == (Decimal("6"), 600)
