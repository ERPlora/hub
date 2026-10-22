"""Several people at once on the same day, the same payment or the same name: real sessions in threads,
real row locks (WORKBOOK «Cómo está hecho»).

The old module proved 30 creations at once without a repeated reference (payments#1/#2); here the
counter's row is raised with ``UPDATE … RETURNING`` in each payment's transaction. Whoever comes first
wins a step; the other one waits for it and is refused with the real reason.
"""

import threading
import uuid

import pytest
from django.db import connection
from django.utils import timezone
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import get

from apps.payment.models import Payment, PaymentCounter, PaymentMethod

from .conftest import ctx_for, make_method, make_payment

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

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list[str]:
    """``ok`` per success, the domain code per refusal, the class name per unexpected failure (an
    ``IntegrityError`` from a repeated reference is not «ok»)."""
    return sorted(
        result.code
        if isinstance(result, OperationError)
        else type(result).__name__
        if isinstance(result, Exception)
        else "ok"
        for result in results
    )


def test_ten_payments_at_once_never_repeat_a_reference():
    # One method per payment (the method's lock must not be what queues them) and the day's counter
    # already there (its creation must not be what queues them either): only the counter's own row
    # lock keeps two numbers apart. A read-add-save counter fails this test.
    PaymentCounter.objects.create(day=timezone.localdate())

    def record(method):
        return lambda: run(
            "payment.payment.create",
            {
                "method_id": str(method.id),
                "payment_date": "2026-10-10",
                "amount": 100,
                "beneficiary_name": "Proveedor",
            },
        )

    methods = [make_method(f"Account {n}") for n in range(10)]
    results = at_once(*[record(method) for method in methods])
    assert codes(results) == ["ok"] * 10
    numbers = sorted(int(result.reference.rsplit("-", 1)[1]) for result in results)
    assert numbers == list(range(1, 11))
    assert Payment.objects.count() == 10


def test_two_approvals_at_once_one_wins_and_the_other_hears_why():
    payment = make_payment(make_method())
    approve = lambda: run("payment.payment.approve", {"id": str(payment.id)})  # noqa: E731
    assert codes(at_once(approve, approve)) == ["ok", "payment.invalid_transition"]


def test_completing_and_cancelling_at_once_never_leave_both():
    payment = make_payment(make_method(), status="sent")
    results = at_once(
        lambda: run("payment.payment.mark_completed", {"id": str(payment.id)}),
        lambda: run(
            "payment.payment.cancel", {"id": str(payment.id), "reason": "late"}
        ),
    )
    final = Payment.objects.get(pk=payment.pk)
    if final.status == "completed":
        assert codes(results) == ["ok", "payment.not_cancellable"]
        assert final.cancel_reason == ""
    else:
        assert final.status == "cancelled"
        assert codes(results) == ["ok", "payment.invalid_transition"]


def test_the_same_attempt_twice_at_once_records_one_payment():
    # A double tap or a retry racing the first send (payments#8): neither sees the other's payment yet,
    # the second one waits for the first and then answers that one, without a second number or notice.
    method = make_method("BBVA account")
    PaymentCounter.objects.create(day=timezone.localdate())
    key = str(uuid.uuid4())

    def send():
        return run(
            "payment.payment.create",
            {
                "method_id": str(method.id),
                "payment_date": "2026-10-10",
                "amount": 100,
                "beneficiary_name": "Proveedor",
                "idempotency_key": key,
            },
        )

    results = at_once(send, send)
    assert codes(results) == ["ok", "ok"]
    assert results[0].id == results[1].id
    assert Payment.objects.count() == 1
    assert PaymentCounter.objects.get(day=timezone.localdate()).last == 1
    assert OutboxEvent.objects.filter(name="payment.payment.created").count() == 1


def test_two_methods_with_one_name_at_once():
    create = lambda: run("payment.method.create", {"name": "Cash drawer"})  # noqa: E731
    assert codes(at_once(create, create)) == ["ok", "payment.method_exists"]
    assert PaymentMethod.objects.count() == 1
