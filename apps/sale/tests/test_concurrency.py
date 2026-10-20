"""Two devices at once (SALE-F01, F06, F22, F30, F31): real sessions in threads, real row locks.

The day's counter numbers every sale once and never leaves a hole; two charges of the same check, a void
and a refund of the same sale, or two refunds of the last units of a line: whichever comes first wins and
the other is refused whole.

The Hub admin's «Delete» of an open check that a write holds waits for it and takes what it left (or answers
«Cannot delete» when a sale charged it); a write that comes second finds it gone. Its «Delete» of a department or a
payment method that a write names waits for the write and answers «Cannot delete»; a write that comes second refuses
it as one that never was.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import Client
from django.utils import timezone
from live.context import system_context
from live.errors import OperationError

from apps.customer.models import Customer
from apps.customer.tests.conftest import card_deleted_on_screen, card_protected, reads, writes
from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    Refund,
    Sale,
    SaleCounter,
)
from apps.sale.tests.conftest import A, run

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("factory_data")]


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


# ── The Hub admin's «Delete» of an open check that a write holds ─────────────────────────────────
#
# Every write on an open check locks it and then adds to what hangs from it or changes it: a line, a line split
# in units, lines it moves to another check or brings from one, the sale that charges it (which protects it).
# Django's «Delete» gathered the check's lines before the write committed and deleted the check after: it missed
# the line the write added and failed at its COMMIT (``IntegrityError``), deleted the lines the write had moved to
# another check, or waited for the write in a circle (``deadlock detected``): a 500 for the staff or for the
# till. Locked first (``lock_orders``), it waits for the write and then takes what the write left, or answers
# «Cannot delete» when a sale charged the check; a write that comes second finds it gone.

#: How the platform staff delete: from the check's delete page, or with the list's «Delete selected».
HOW = ["page", "list"]

#: How long a session waits for another one to queue behind its lock.
WAIT_LIMIT = 10


def _waited_for() -> bool:
    """Whether another session waits for a lock this one holds."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pg_backend_pid() = ANY (pg_blocking_pids(pid)))"
        )
        return cursor.fetchone()[0]


def _waiting() -> int:
    """How many other sessions on this database wait for a lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            " AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
        )
        return cursor.fetchone()[0]


def locks(table: str) -> Callable[[str], bool]:
    """Whether a statement locks rows of ``table``."""
    return lambda sql: f'FROM "{table}"' in sql and "FOR UPDATE" in sql


@pytest.fixture
def hub_staff(db) -> Client:
    """The platform staff, signed in to the Hub admin."""
    staff = get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )
    client = Client()
    client.force_login(staff)
    return client


def admin_delete(client: Client, how: str, *targets):
    """The Hub admin's «Delete» of ``targets`` (one for its page), ``how`` it says (see ``HOW``); it returns
    the answer."""
    meta = type(targets[0])._meta
    changelist = f"/admin/{meta.app_label}/{meta.model_name}/"
    if how == "page":
        [target] = targets
        url, data = f"{changelist}{target.pk}/delete/", {"post": "yes"}
    else:
        url, data = changelist, {
            "action": "delete_selected",
            "_selected_action": [str(target.pk) for target in targets],
            "post": "yes",
        }
    return lambda: client.post(
        url, data, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en"
    )


@contextmanager
def meanwhile(after: Callable[[str], bool], call):
    """Runs ``call`` in another session right after the first statement of this one for which ``after``
    holds; this one goes on once ``call`` waits for what it holds (or has ended). Yields its outcome (an
    error raised, a 500 included, is the outcome)."""
    outcome: list = []

    def other():
        try:
            outcome.append(call())
        except Exception as error:  # reported to the test
            outcome.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=other)

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if thread.ident is None and after(sql):
            thread.start()
            deadline = time.monotonic() + WAIT_LIMIT
            while thread.is_alive() and not _waited_for() and time.monotonic() < deadline:
                time.sleep(0.02)
        return result

    try:
        with connection.execute_wrapper(wrapper):
            yield outcome
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "this session never locked"


def in_turn(row, *calls) -> list:
    """Holds ``row`` locked in this session and starts ``calls`` in their own sessions, each once the ones before
    wait for a lock, so they queue for ``row`` in that order; then lets it go. Their outcomes (an error raised,
    a 500 included, is the outcome)."""
    outcomes: list = [None] * len(calls)

    def other(index, call):
        try:
            outcomes[index] = call()
        except Exception as error:  # reported to the test
            outcomes[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=other, args=(i, call)) for i, call in enumerate(calls)]
    with transaction.atomic():
        list(type(row).objects.select_for_update().filter(pk=row.pk))
        for queued, thread in enumerate(threads, start=1):
            thread.start()
            deadline = time.monotonic() + WAIT_LIMIT
            while thread.is_alive() and _waiting() < queued and time.monotonic() < deadline:
                time.sleep(0.02)
    for thread in threads:
        thread.join(30)
    return outcomes


def a_check(label: str = "", quantity: str = "2"):
    """An open check with two coffees on one line."""
    return run("sale.order.open", {"label": label, "lines": [{"product": "COF", "quantity": quantity}]})


def merged(source, target):
    return run("sale.order.merge", {"from_order_id": str(source.id), "to_order_id": str(target.id)})


#: Writes that lock the check and then add to it or change what hangs from it; what each leaves is checked below.
CHECK_WRITES = {
    "a line": lambda check: run("sale.order.add_line", {"order_id": str(check.id), "product": "COF"}),
    "a line split in units": lambda check: run(
        "sale.order.split_line", {"order_id": str(check.id), "line_id": str(check.lines[0].id)}
    ),
    "a changed line": lambda check: run(
        "sale.order.update_line",
        {"order_id": str(check.id), "line_id": str(check.lines[0].id), "quantity": "3"},
    ),
    "lines brought from another check": lambda check: merged(a_check("other"), check),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CHECK_WRITES))
def test_the_hub_admin_deletes_a_check_a_write_holds_once_it_is_written(coffee, hub_staff, write, how):
    check = a_check()
    deletion = admin_delete(hub_staff, how, Order.objects.get(pk=check.id))
    with meanwhile(locks("sale_order"), deletion) as answers:
        CHECK_WRITES[write](check)
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Order.objects.filter(pk=check.id).exists()
    # What the write added went with the check: no line is left without one.
    assert not OrderLine.objects.filter(order_id=check.id).exists()


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_deletes_a_check_a_split_holds_and_the_new_check_keeps_its_lines(coffee, hub_staff, how):
    check = a_check()
    [line] = check.lines
    deletion = admin_delete(hub_staff, how, Order.objects.get(pk=check.id))
    with meanwhile(locks("sale_order"), deletion) as answers:
        out = run("sale.order.split", {"order_id": str(check.id), "line_ids": [str(line.id)]})
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Order.objects.filter(pk=check.id).exists()
    assert list(OrderLine.objects.filter(order_id=out.new_order.id).values_list("id", flat=True)) == [line.id]


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_deletes_a_check_a_merge_empties_and_the_other_keeps_its_lines(coffee, hub_staff, how):
    source, target = a_check("source"), a_check("target")
    deletion = admin_delete(hub_staff, how, Order.objects.get(pk=source.id))
    with meanwhile(locks("sale_order"), deletion) as answers:
        merged(source, target)
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Order.objects.filter(pk=source.id).exists()
    assert OrderLine.objects.filter(order_id=target.id).count() == 2


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_cannot_delete_a_check_a_charge_holds(coffee, hub_staff, how):
    check = a_check()
    deletion = admin_delete(hub_staff, how, Order.objects.get(pk=check.id))
    with meanwhile(locks("sale_order"), deletion) as answers:
        sale = charge("admin-race-charge", order_id=str(check.id))()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Cannot delete open check")
    assert len(answer.context["protected"]) == 1
    assert Order.objects.get(pk=check.id).status == "completed"
    assert Sale.objects.get(pk=sale.id).order_id == check.id


def test_the_hub_admin_confirmation_page_of_a_check_a_write_holds_does_not_wait(coffee, hub_staff):
    """The check's delete page (a GET, before the staff confirm) does not lock the check: it answers while a
    write still holds it; only the confirmed deletion (a POST) waits for the write."""
    check = a_check()
    meta = Order._meta
    url = f"/admin/{meta.app_label}/{meta.model_name}/{check.id}/delete/"
    outcome: list = []

    def other():
        try:
            outcome.append(hub_staff.get(url, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en"))
        except Exception as error:  # reported to the test
            outcome.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=other)
    with transaction.atomic():
        list(Order.objects.select_for_update().filter(pk=check.id))
        thread.start()
        thread.join(WAIT_LIMIT)
        answered_while_held = not thread.is_alive()
    thread.join(30)
    assert answered_while_held, "the delete page waited for the write that held the check"
    [answer] = outcome
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Delete")
    assert Order.objects.filter(pk=check.id).exists()


#: Writes that come second: each finds the check gone.
SECOND_WRITES = {
    "a line": CHECK_WRITES["a line"],
    "a charge": lambda check: charge("admin-race-late-charge", order_id=str(check.id))(),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(SECOND_WRITES))
def test_a_write_while_the_hub_admin_deletes_the_check_finds_it_gone(coffee, hub_staff, write, how):
    check = a_check()
    with meanwhile(locks("sale_order"), lambda: SECOND_WRITES[write](check)) as outcomes:
        answer = admin_delete(hub_staff, how, Order.objects.get(pk=check.id))()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "sale.order_not_found")
    assert not Order.objects.filter(pk=check.id).exists()
    assert not Sale.objects.exists()


@pytest.mark.parametrize("first_in_line", ["deletion", "merge"])
def test_a_merge_and_the_hub_admin_deleting_both_checks_never_wait_in_a_circle(coffee, hub_staff, first_in_line):
    first, second = sorted([a_check("one"), a_check("two")], key=lambda check: check.id)
    rows = Order.objects.filter(pk__in=[first.id, second.id]).order_by("-id")
    # The list names them the other way round from their ids, and the merge goes from the second to the first.
    deletion = admin_delete(hub_staff, "list", *rows)
    merge = lambda: merged(second, first)  # noqa: E731
    held = Order.objects.get(pk=first.id)
    if first_in_line == "deletion":
        deleted, written = in_turn(held, deletion, merge)
    else:
        written, deleted = in_turn(held, merge, deletion)
    assert not isinstance(deleted, Exception), deleted
    assert deleted.status_code == 302
    assert not Order.objects.filter(pk__in=[first.id, second.id]).exists()
    assert not OrderLine.objects.exists()
    if first_in_line == "deletion":
        assert isinstance(written, OperationError), written
        assert (written.status, written.code) == (404, "sale.order_not_found")
    else:
        assert not isinstance(written, Exception), written


# ── The Hub admin's «Delete» of a department or a payment method that a write names ─────────────────
#
# An open-price line points at its department and a tender at its payment method (``PROTECT``). A write read the
# row and then wrote what points at it; Django's «Delete» checked what protects the row before the write committed
# and deleted it after: the write failed at its COMMIT (``IntegrityError``, a 500 at the till), or the deletion did
# when the write committed first. The write holds the row (``FOR KEY SHARE``) and the deletion locks it before it
# checks (``lock_rows``): whichever comes second waits. The deletion then answers «Cannot delete», or the write
# refuses the row as one that never was (its 422 or 409 for an unknown one).


def a_department(name: str = "Fruit") -> Department:
    """A department of the open price that no line names yet."""
    made = run("sale.department.create", {"name": name, "tax_category_key": "product.super_reduced"})
    return Department.objects.get(pk=made.id)


def a_method(name: str = "Bizum") -> PaymentMethod:
    """A payment method that no tender names yet."""
    made = run("sale.payment_method.create", {"name": name, "type": "other"})
    return PaymentMethod.objects.get(pk=made.id)


def inserts(table: str) -> Callable[[str], bool]:
    """Whether a statement writes rows of ``table``."""
    return lambda sql: sql.startswith(f'INSERT INTO "{table}"')


def reads(table: str) -> Callable[[str], bool]:
    """Whether a statement reads rows of ``table`` (the deletion looking for what protects a row)."""
    return lambda sql: sql.startswith("SELECT") and f'FROM "{table}"' in sql


def open_price(department: Department, cents: int = 250) -> dict:
    return {"department_id": str(department.id), "unit_price": cents}


def _open_price_on_a_check(department):
    check = a_check()
    return lambda: run("sale.order.add_open_line", {"order_id": str(check.id), **open_price(department)})


#: Writes that name a department for the open-price line they add; each is prepared before the race and returns
#: the call that writes.
DEPARTMENT_WRITES = {
    "an open-price line added to a check": _open_price_on_a_check,
    "a check opened with an open-price line": lambda department: lambda: run(
        "sale.order.open", {"open_lines": [open_price(department)]}
    ),
    "a counter sale of an open-price line": lambda department: charge(
        "admin-race-open-price", open_lines=[open_price(department)]
    ),
}


def _charge_of_a_check(method):
    check = a_check()
    return charge("admin-race-method-check", order_id=str(check.id), payments=[{"method_id": str(method.id)}])


def _refund_by(method):
    sale = charge("admin-race-method-sold", lines=[{"product": "COF"}])()
    allocation = {"payment_id": str(sale.payments[0].id), "amount": 150, "to_method_id": str(method.id)}
    return lambda: run("sale.sale.refund", {"sale_id": str(sale.id), "reason": "back", "allocations": [allocation]})


#: Writes that name a payment method for the tender they record: how each is prepared, the table of that tender and
#: the code it gives for a method that is not there.
METHOD_WRITES = {
    "a charge of a check": (_charge_of_a_check, "sale_salepayment", "sale.payment_method_not_available"),
    "a counter sale": (
        lambda method: charge(
            "admin-race-method-counter", lines=[{"product": "COF"}], payments=[{"method_id": str(method.id)}]
        ),
        "sale_salepayment",
        "sale.payment_method_not_available",
    ),
    "a refund by another method": (_refund_by, "sale_refundpayment", "sale.refund_method_unavailable"),
}


def cannot_delete(answer, model, rows: int = 1) -> None:
    """The deletion answered «Cannot delete» the ``rows`` rows of ``model``, each protected by what a write wrote."""
    assert not isinstance(answer, Exception), answer
    name = model._meta.verbose_name if rows == 1 else model._meta.verbose_name_plural
    assert (answer.status_code, str(answer.context["title"])) == (200, f"Cannot delete {name}")
    assert len(answer.context["protected"]) == rows


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(DEPARTMENT_WRITES))
def test_the_hub_admin_cannot_delete_a_department_a_write_names_once_it_is_written(coffee, hub_staff, write, how):
    fruit = a_department()
    written = DEPARTMENT_WRITES[write](fruit)
    with meanwhile(inserts("sale_orderline"), admin_delete(hub_staff, how, fruit)) as answers:
        written()
    [answer] = answers
    cannot_delete(answer, Department)
    assert Department.objects.filter(pk=fruit.id).exists()
    assert OrderLine.objects.filter(department=fruit).count() == 1


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(DEPARTMENT_WRITES))
def test_a_write_naming_a_department_the_hub_admin_deletes_refuses_it_as_unknown(coffee, hub_staff, write, how):
    fruit = a_department()
    written = DEPARTMENT_WRITES[write](fruit)
    lines, sales = OrderLine.objects.count(), Sale.objects.count()
    with meanwhile(reads("sale_orderline"), written) as outcomes:
        answer = admin_delete(hub_staff, how, fruit)()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, set(outcome.fields)) == (422, "invalid_field", {"department_id"})
    assert not Department.objects.filter(pk=fruit.id).exists()
    assert (OrderLine.objects.count(), Sale.objects.count()) == (lines, sales)


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(METHOD_WRITES))
def test_the_hub_admin_cannot_delete_a_payment_method_a_write_names_once_it_is_written(coffee, hub_staff, write, how):
    prepare, table, _code = METHOD_WRITES[write]
    bizum = a_method()
    written = prepare(bizum)
    with meanwhile(inserts(table), admin_delete(hub_staff, how, bizum)) as answers:
        written()
    [answer] = answers
    cannot_delete(answer, PaymentMethod)
    assert PaymentMethod.objects.filter(pk=bizum.id).exists()


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(METHOD_WRITES))
def test_a_write_naming_a_payment_method_the_hub_admin_deletes_refuses_it_as_unknown(coffee, hub_staff, write, how):
    prepare, table, code = METHOD_WRITES[write]
    bizum = a_method()
    written = prepare(bizum)
    sales, refunds = Sale.objects.count(), Refund.objects.count()
    # The write starts as the deletion looks for the tenders like the one it records.
    with meanwhile(reads(table), written) as outcomes:
        answer = admin_delete(hub_staff, how, bizum)()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (409, code)
    assert not PaymentMethod.objects.filter(pk=bizum.id).exists()
    assert (Sale.objects.count(), Refund.objects.count()) == (sales, refunds)


def _two(make) -> tuple:
    """Two rows by ``make``, by id, whose names sort the other way round: the tables read in position and name
    order unless told otherwise, so only an explicit id order takes them first-then-second."""
    return make("Zeta"), make("Alpha")


@pytest.mark.parametrize("first_in_line", ["deletion", "write"])
def test_a_sale_and_the_hub_admin_deleting_both_its_departments_never_wait_in_a_circle(
    coffee, hub_staff, first_in_line
):
    first, second = _two(a_department)
    # The sale and the list name them the other way round from their ids.
    sale = charge("admin-race-two-departments", open_lines=[open_price(second), open_price(first)])
    deletion = admin_delete(hub_staff, "list", second, first)
    if first_in_line == "deletion":
        deleted, written = in_turn(first, deletion, sale)
    else:
        written, deleted = in_turn(first, sale, deletion)
    assert not isinstance(deleted, Exception), deleted
    assert not isinstance(written, Exception) or isinstance(written, OperationError), written
    if first_in_line == "deletion":
        assert deleted.status_code == 302
        assert (written.status, written.code) == (422, "invalid_field")
        assert not Department.objects.filter(pk__in=[first.id, second.id]).exists()
    else:
        cannot_delete(deleted, Department, rows=2)
        assert OrderLine.objects.filter(sale_id=written.id).count() == 2


@pytest.mark.parametrize("first_in_line", ["deletion", "write"])
def test_a_sale_and_the_hub_admin_deleting_both_its_payment_methods_never_wait_in_a_circle(
    coffee, hub_staff, first_in_line
):
    first, second = _two(a_method)
    # The sale and the list name them the other way round from their ids.
    payments = [{"method_id": str(second.id), "amount": 100}, {"method_id": str(first.id)}]
    sale = charge("admin-race-two-methods", lines=[{"product": "COF"}], payments=payments)
    deletion = admin_delete(hub_staff, "list", second, first)
    if first_in_line == "deletion":
        deleted, written = in_turn(first, deletion, sale)
    else:
        written, deleted = in_turn(first, sale, deletion)
    assert not isinstance(deleted, Exception), deleted
    assert not isinstance(written, Exception) or isinstance(written, OperationError), written
    if first_in_line == "deletion":
        assert deleted.status_code == 302
        assert (written.status, written.code) == (409, "sale.payment_method_not_available")
        assert not PaymentMethod.objects.filter(pk__in=[first.id, second.id]).exists()
    else:
        cannot_delete(deleted, PaymentMethod, rows=2)
        assert Sale.objects.get(pk=written.id).payments.count() == 2


@pytest.mark.parametrize("make", [a_department, a_method], ids=["department", "payment method"])
def test_the_hub_admin_delete_page_of_a_row_a_write_holds_does_not_wait(coffee, hub_staff, make):
    """The delete page of a department or a payment method (a GET, before the staff confirm) does not lock it: it
    answers while a write still holds it; only the confirmed deletion (a POST) waits for the write."""
    row = make()
    meta = type(row)._meta
    url = f"/admin/{meta.app_label}/{meta.model_name}/{row.pk}/delete/"
    outcome: list = []

    def other():
        try:
            outcome.append(hub_staff.get(url, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en"))
        except Exception as error:  # reported to the test
            outcome.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=other)
    with transaction.atomic():
        list(type(row).objects.select_for_update().filter(pk=row.pk))
        thread.start()
        thread.join(WAIT_LIMIT)
        answered_while_held = not thread.is_alive()
    thread.join(30)
    assert answered_while_held, "the delete page waited for the write that held the row"
    [answer] = outcome
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Delete")
    assert type(row).objects.filter(pk=row.pk).exists()


# ── The Hub admin's «Delete» of the customer's card while a charge links it ──────────────────────
#
# A charge with a customer finds the card and then writes the sale that points at it. The Hub admin's «Delete» of
# that card between the two found nothing protecting it and deleted it: the charge then failed at its COMMIT (an
# IntegrityError, a 500, and nothing charged). The charge locks the card when it finds it, before the check, as
# the deletion does: the deletion waits for it and answers «Cannot delete», since the sale protects the card; a
# charge that comes second waits for the deletion and is told the card is gone, with nothing charged.


def counter_charge(card):
    data = {"idempotency_key": "card-counter", "lines": [{"product": "COF"}]}
    return lambda: run("sale.sale.complete", {**data, "customer_id": str(card.id)})


def check_charge(card):
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    data = {"idempotency_key": "card-check", "order_id": str(order.id), "order_version": order.version}
    return lambda: run("sale.sale.complete", {**data, "customer_id": str(card.id)})


#: A counter sale, and the charge of an open check.
CARD_CHARGES = {"counter": counter_charge, "check": check_charge}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("charge_of", sorted(CARD_CHARGES))
def test_the_hub_admin_cannot_delete_a_card_a_charge_links_meanwhile(coffee, charge_of, how):
    card = Customer.objects.create(name="Ana García")
    charge_it = CARD_CHARGES[charge_of](card)
    with card_deleted_on_screen(card, how, writes("sale_sale")) as answers:
        charge_it()
    [answer] = answers
    assert card_protected(answer)
    assert Sale.objects.get().customer_id == card.id


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("charge_of", sorted(CARD_CHARGES))
def test_a_charge_whose_card_the_hub_admin_deletes_first_is_told_it_is_gone(coffee, charge_of, how):
    card = Customer.objects.create(name="Ana García")
    charge_it = CARD_CHARGES[charge_of](card)
    with card_deleted_on_screen(card, how, reads("customer_customer")) as answers:
        with pytest.raises(OperationError) as refused:
            charge_it()
    [answer] = answers
    assert answer.status_code == 302
    assert (refused.value.status, refused.value.code) == (404, "customer.customer_unavailable")
    assert not Customer.objects.filter(pk=card.pk).exists()
    assert not Sale.objects.exists()


# The merge of two cards moves the absorbed card's sales to the card that stays, later, as a reaction: the Hub
# admin may have deleted that card in between (nothing protected it), or delete it while the reaction moves them.
# The reaction locks the card that stays first: gone, nothing moves (the sales keep the card they were charged
# to) instead of failing for ever at its COMMIT; there, the deletion waits and answers «Cannot delete».


def _merged_into_marta(coffee):
    ana = Customer.objects.create(name="Ana García")
    sale = counter_charge(ana)()
    marta = Customer.objects.create(name="Marta Gil")
    data = {"id": str(marta.id), "absorbed_id": str(ana.id)}
    return ana, Sale.objects.get(pk=sale.id), marta, lambda: run("sale.customer.reassign", data, system_context(A))


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_cannot_delete_the_card_a_merge_moves_the_sales_to_meanwhile(coffee, how):
    _, sale, marta, move = _merged_into_marta(coffee)
    with card_deleted_on_screen(marta, how, writes("sale_sale")) as answers:
        move()
    [answer] = answers
    assert card_protected(answer)
    sale.refresh_from_db()
    assert sale.customer_id == marta.id


@pytest.mark.parametrize("how", HOW)
def test_a_merge_into_a_card_the_hub_admin_deleted_moves_no_sale(coffee, hub_staff, how):
    ana, sale, marta, move = _merged_into_marta(coffee)
    assert admin_delete(hub_staff, how, marta)().status_code == 302
    assert move().moved == 0
    sale.refresh_from_db()
    assert sale.customer_id == ana.id
