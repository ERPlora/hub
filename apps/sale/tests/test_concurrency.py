"""Two devices at once (SALE-F01, F06, F22, F30, F31): real sessions in threads, real row locks.

The day's counter numbers every sale once and never leaves a hole; two charges of the same check, a void
and a refund of the same sale, or two refunds of the last units of a line: whichever comes first wins and
the other is refused whole.
"""

import threading

import pytest
from django.db import connection
from django.utils import timezone
from live.context import system_context
from live.errors import OperationError

from apps.sale.models import Order, Sale, SaleCounter
from apps.sale.tests.conftest import A, run

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def factory_data(transactional_db):
    """A transactional test starts from a flushed database: tax's factory catalogue and the factory
    payment methods are planted again, as their migrations do (idempotent)."""
    from importlib import import_module

    from django.apps import apps as registry

    with connection.schema_editor() as editor:
        for module in ("apps.tax.migrations.0002_factory_catalogue", "apps.tax.migrations.0005_retail_alcohol", "apps.sale.migrations.0002_factory_payment_methods"):
            import_module(module).plant(registry, editor)


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

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list:
    return sorted(getattr(result, "code", "ok") for result in results)


@pytest.fixture
def coffee():
    return run(
        "inventory.product.create",
        {
            "name": "Coffee",
            "sku": "COF",
            "price": 150,
            "tax_category_key": "restaurant.drink",
        },
        system_context(A),
    )


def charge(key, **data):
    return lambda: run("sale.sale.complete", {"idempotency_key": key, **data})


def test_the_counter_numbers_every_sale_once_and_leaves_no_hole(coffee):
    results = at_once(
        *(charge(f"race-number-{i:02}", lines=[{"product": "COF"}]) for i in range(6))
    )
    assert codes(results) == ["ok"] * 6
    day = timezone.localdate()
    assert sorted(result.number for result in results) == [
        f"{day:%Y%m%d}-{n:04d}" for n in range(1, 7)
    ]
    assert SaleCounter.objects.get(day=day).last == 6


def test_the_same_attempt_twice_at_once_charges_once_and_burns_no_number(coffee):
    results = at_once(
        charge("race-same-key", lines=[{"product": "COF"}]),
        charge("race-same-key", lines=[{"product": "COF"}]),
    )
    assert Sale.objects.count() == 1
    assert {
        getattr(result, "code", None) or ("already" if result.already else "ok")
        for result in results
    } <= {
        "ok",
        "already",
        "sale.checkout_in_progress",
    }
    assert SaleCounter.objects.get().last == 1


def test_two_charges_of_the_same_check_charge_it_once(coffee):
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "2"}]})
    results = at_once(
        charge("race-check-1", order_id=str(order.id)),
        charge("race-check-2", order_id=str(order.id)),
    )
    assert codes(results) == ["ok", "sale.order_changed"]
    assert (
        Sale.objects.count() == 1
        and Order.objects.get(pk=order.id).status == "completed"
    )


def test_a_change_of_the_check_and_its_charge_at_once(coffee):
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    line = str(order.lines[0].id)
    update = lambda: run(
        "sale.order.update_line",
        {"order_id": str(order.id), "line_id": line, "quantity": "3"},
    )  # noqa: E731
    results = at_once(
        charge("race-change-1", order_id=str(order.id), order_version=order.version),
        update,
    )
    # Either the charge took the check as it was (and the change came too late), or the change won.
    assert codes(results) == ["ok", "sale.order_changed"]
    sale = Sale.objects.first()
    if sale is not None:
        assert sale.total == 150
    else:
        assert Order.objects.get(pk=order.id).provisional_total == 450


def test_a_void_and_a_refund_of_the_same_sale_at_once(coffee):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "race-void-0001",
            "lines": [{"product": "COF"}],
            "payments": [{"method": "card"}],
        },
    )
    void = lambda: run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong"})  # noqa: E731
    refund = lambda: run(  # noqa: E731
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "back",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 75}],
        },
    )
    results = at_once(void, refund)
    assert codes(results) in (
        ["ok", "sale.refund_requires_completed"],
        ["ok", "sale.sale_already_refunded"],
    )
    stored = Sale.objects.get(pk=sale.id)
    assert (stored.status, stored.refunded_total) in (("voided", 0), ("completed", 75))


def test_two_refunds_of_the_last_units_of_a_line_at_once(coffee):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "race-units-001",
            "lines": [{"product": "COF", "quantity": "2"}],
            "payments": [{"method": "card"}],
        },
    )
    leg, line = str(sale.payments[0].id), str(sale.lines[0].id)

    def refund():
        return run(
            "sale.sale.refund",
            {
                "sale_id": str(sale.id),
                "reason": "back",
                "allocations": [{"payment_id": leg, "amount": 100}],
                "lines": [{"line_id": line, "quantity": "2"}],
            },
        )

    results = at_once(refund, refund)
    assert codes(results) == ["ok", "sale.refund_line_already_returned"]
    assert Sale.objects.get(pk=sale.id).refunded_total == 100
