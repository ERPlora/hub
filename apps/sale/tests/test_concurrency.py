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


def answers(results) -> list:
    """``ok`` for a sale charged now, ``already`` for the one an earlier attempt charged, else the code."""
    return sorted(getattr(r, "code", None) or ("already" if r.already else "ok") for r in results)


def test_the_same_attempt_twice_at_once_charges_once_and_burns_no_number(coffee):
    results = at_once(
        charge("race-same-key", lines=[{"product": "COF"}]),
        charge("race-same-key", lines=[{"product": "COF"}]),
    )
    # Whoever waited gets the very sale the other charged: never «nothing was charged».
    assert answers(results) == ["already", "ok"]
    assert results[0].id == results[1].id
    assert Sale.objects.count() == 1
    assert SaleCounter.objects.get().last == 1


def test_the_same_attempt_on_a_check_twice_at_once_answers_the_sale_both_times(coffee):
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "2"}]})
    results = at_once(
        charge("race-check-key", order_id=str(order.id), order_version=order.version),
        charge("race-check-key", order_id=str(order.id), order_version=order.version),
    )
    assert answers(results) == ["already", "ok"]
    assert results[0].id == results[1].id and Sale.objects.count() == 1
    assert Order.objects.get(pk=order.id).status == "completed"


def test_the_same_refund_attempt_twice_at_once_refunds_once(coffee):
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "race-refund-001", "lines": [{"product": "COF", "quantity": "2"}], "payments": [{"method": "card"}]},
    )
    data = {
        "sale_id": str(sale.id),
        "reason": "back",
        "idempotency_key": "race-refund-key",
        "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 300}],
        "lines": [{"line_id": str(sale.lines[0].id)}],
    }
    results = at_once(lambda: run("sale.sale.refund", data), lambda: run("sale.sale.refund", data))
    assert answers(results) == ["already", "ok"]
    assert Sale.objects.get(pk=sale.id).refunded_total == 300


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


# ── Vouchers at the till (SALE-F27, F32) ────────────────────────────────────────────────────────


def svc(name, data):
    from live.operations import get

    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


@pytest.fixture
def last_session():
    """Lucía's voucher of one haircut, and the haircut, made by Services."""
    haircut = svc(
        "service.service.create",
        {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
    )
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"}, system_context(A))
    package = svc(
        "service.package.create",
        {"name": "Bono 1", "max_uses": 1, "items": [{"service_id": str(haircut.id)}]},
    )
    grant = svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id)},
    )
    return haircut, lucia, grant


def apply(order, grant):
    return lambda: run(
        "sale.order.apply_voucher",
        {
            "order_id": str(order.id),
            "line_id": str(order.lines[0].id),
            "grant_id": str(grant.id),
        },
    )


def test_two_tills_paying_with_the_last_session_one_wins_and_the_other_hears_why(
    last_session,
):
    from apps.service.models import Redemption

    haircut, _lucia, grant = last_session
    first = run("sale.order.open", {"service_lines": [{"service_id": str(haircut.id)}]})
    second = run("sale.order.open", {"service_lines": [{"service_id": str(haircut.id)}]})
    results = at_once(apply(first, grant), apply(second, grant))
    assert codes(results) == ["ok", "service.grant_no_uses_left"]
    assert Redemption.objects.filter(status="held").count() == 1
    covered = [
        line.voucher_session_id
        for line in Order.objects.get(pk=first.id).lines.all()
    ] + [line.voucher_session_id for line in Order.objects.get(pk=second.id).lines.all()]
    assert len([session for session in covered if session]) == 1


def test_charging_a_check_and_voiding_it_at_once_spend_or_release_its_session(
    last_session,
):
    from apps.service.models import Redemption

    haircut, lucia, grant = last_session
    order = run("sale.order.open", {"service_lines": [{"service_id": str(haircut.id)}]})
    apply(order, grant)()
    results = at_once(
        charge("race-voucher-01", order_id=str(order.id), customer_id=str(lucia.id)),
        lambda: run("sale.order.void", {"order_id": str(order.id)}),
    )
    assert codes(results) in (
        ["ok", "sale.order_changed"],
        ["ok", "sale.order_unavailable"],
    )
    [session] = Redemption.objects.all()
    if Sale.objects.exists():
        assert session.status == "consumed"
        assert Order.objects.get(pk=order.id).status == "completed"
    else:
        assert session.status == "released"
        assert Order.objects.get(pk=order.id).status == "voided"


def test_voiding_and_refunding_a_sale_paid_with_a_voucher_at_once_give_the_session_back_once(
    last_session,
):
    from apps.service.models import Redemption

    haircut, lucia, grant = last_session
    order = run("sale.order.open", {"service_lines": [{"service_id": str(haircut.id)}]})
    apply(order, grant)()
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "race-voucher-02", "order_id": str(order.id), "customer_id": str(lucia.id)},
    )
    line = sale.lines[0]
    results = at_once(
        lambda: run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong"}),
        lambda: run(
            "sale.sale.refund",
            {
                "sale_id": str(sale.id),
                "reason": "did not come",
                "allocations": [],
                "lines": [{"line_id": str(line.id)}],
            },
        ),
    )
    assert codes(results) in (
        ["ok", "sale.refund_requires_completed"],
        ["ok", "sale.sale_already_refunded"],
    )
    [session] = Redemption.objects.all()
    assert session.status == "returned"


def test_two_charges_of_one_appointment_at_once_open_one_check(coffee):
    # «Charge» tapped on two devices for the same appointment: one check, and both answer it.
    from uuid import uuid7

    appointment = str(uuid7())

    def open_check():
        return run(
            "sale.order.open",
            {"appointment_id": appointment, "lines": [{"product": "COF"}]},
        )

    results = at_once(open_check, open_check)
    assert answers(results) == ["already", "ok"]
    assert results[0].id == results[1].id
    assert Order.objects.filter(appointment_id=appointment).count() == 1
