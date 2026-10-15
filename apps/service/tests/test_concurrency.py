"""Two tills at once on the same voucher, and two saves of the same name: real sessions in threads,
real row locks (WORKBOOK «Concurrencia»).

Whichever comes first wins; the other one waits for it and is refused with the real reason, never
with a broken balance or a duplicated name.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError
from live.operations import get

from apps.service.models import Assignment, Category, Redemption

from .conftest import (
    ctx_for,
    make_category,
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_service,
    make_tax,
)

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
    return sorted(getattr(result, "code", "ok") for result in results)


@pytest.fixture
def cut():
    return make_service("Cut", tax=make_tax())


def test_two_tills_spending_the_last_session_one_wins_and_the_other_hears_why(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    spend = lambda: run(
        "service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)}
    )  # noqa: E731
    assert codes(at_once(spend, spend)) == ["ok", "service.grant_no_uses_left"]
    assert Redemption.objects.count() == 1


def test_a_void_and_a_session_at_once_never_leave_a_used_voucher_voided(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    results = at_once(
        lambda: run(
            "service.grant.void", {"id": str(grant.id), "reason": "wrong customer"}
        ),
        lambda: run("service.grant.redeem", {"id": str(grant.id)}),
    )
    assert codes(results) in (
        ["ok", "service.grant_voided"],
        ["ok", "service.grant_in_use"],
    )
    grant.refresh_from_db()
    assert (grant.voided_at is not None) != Redemption.objects.exists()


def test_a_correction_and_a_session_at_once_never_take_the_balance_below_zero(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    results = at_once(
        lambda: run(
            "service.grant.adjust",
            {"id": str(grant.id), "uses_delta": -1, "reason": "typo"},
        ),
        lambda: run("service.grant.redeem", {"id": str(grant.id)}),
    )
    assert codes(results) in (
        ["ok", "service.grant_no_uses_left"],
        ["ok", "service.grant_adjust_below_used"],
    )
    [row] = run("service.grant.list", {"package_id": str(grant.package_id)}).rows
    assert row.remaining == 0


def test_two_categories_with_the_same_name_at_once_one_is_refused_with_the_409():
    create = lambda: run("service.category.create", {"name": "Hair"})  # noqa: E731
    assert codes(at_once(create, create)) == ["ok", "service.category_name_taken"]
    assert Category.objects.count() == 1


def test_two_main_services_for_the_same_professional_at_once_leave_one(cut):
    colour = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    make_member("Ana", "López")
    results = at_once(
        lambda: run(
            "service.assignment.assign",
            {"service": "Cut", "member": "Ana López", "is_primary": True},
        ),
        lambda: run(
            "service.assignment.assign",
            {"service_id": str(colour.id), "member": "Ana López", "is_primary": True},
        ),
    )
    assert codes(results) == ["ok", "ok"]
    assert Assignment.objects.filter(is_primary=True).count() == 1


def test_two_categories_hung_from_each_other_at_once_one_is_refused():
    a = make_category("Hair")
    b = make_category("Colour")
    results = at_once(
        lambda: run("service.category.update", {"id": str(a.id), "parent_id": str(b.id)}),
        lambda: run("service.category.update", {"id": str(b.id), "parent_id": str(a.id)}),
    )
    assert codes(results) == ["ok", "service.category_cycle"]
    parents = dict(Category.objects.values_list("id", "parent_id"))
    assert parents[a.id] is None or parents[b.id] is None


# ── Sessions of the till (SERVICE-F22–F24) ──────────────────────────────────────────────────


def hold_for(grant, service, line):
    return lambda: run(
        "service.session.hold",
        {"grant_id": str(grant.id), "service_id": str(service.id), "order_line_id": str(line)},
    )


def test_two_tills_holding_the_last_session_for_two_lines_one_wins(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    results = at_once(hold_for(grant, cut, uuid.uuid7()), hold_for(grant, cut, uuid.uuid7()))
    assert codes(results) == ["ok", "service.grant_no_uses_left"]
    assert Redemption.objects.filter(status="held").count() == 1


def test_the_same_line_held_twice_at_once_keeps_one_session(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    line = uuid.uuid7()
    results = at_once(hold_for(grant, cut, line), hold_for(grant, cut, line))
    assert codes(results) == ["ok", "service.line_already_held"]
    assert Redemption.objects.filter(order_line_id=line).count() == 1


def test_a_void_and_a_hold_at_once_never_leave_a_held_session_on_a_voided_voucher(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    results = at_once(
        lambda: run("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"}),
        hold_for(grant, cut, uuid.uuid7()),
    )
    assert codes(results) in (
        ["ok", "service.grant_voided"],
        ["ok", "service.grant_in_use"],
    )
    grant.refresh_from_db()
    assert (grant.voided_at is not None) != Redemption.objects.filter(status="held").exists()


def test_charging_and_releasing_a_session_at_once_do_one_or_the_other(cut):
    import uuid

    customer = make_customer()
    grant = make_grant(make_package("Bono", [cut], max_uses=5), customer)
    held = hold_for(grant, cut, uuid.uuid7())()
    results = at_once(
        lambda: run(
            "service.session.settle",
            {"ids": [str(held.id)], "sale_id": str(uuid.uuid7()), "customer_id": str(customer.id)},
        ),
        lambda: run("service.session.release", {"id": str(held.id)}),
    )
    assert codes(results) in (
        ["ok", "service.session_settled"],
        ["ok", "service.hold_lost"],
    )
    status = Redemption.objects.get(pk=held.id).status
    assert status in ("consumed", "released")
