"""Services and Sales together, no mocks (SERVICE-F22–F27): what a voucher shows and allows while the
till holds, charges, voids and refunds its sessions.

The till's writes are Sales' real operations (they call Services' session operations inside their
own transaction); the voucher, its balance, its options and its movements are read with Services' own
queries.
"""

import datetime as dt
from uuid import uuid7

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get, registry

from apps.service.models import Redemption

from .conftest import HUB_DB, A, ctx_for

pytestmark = HUB_DB


def run(name: str, data: dict, role: str = "hub_admin"):
    op = get(name)
    return op(ctx_for(role), op.input.model_validate(data))


def system(name: str, data: dict):
    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


@pytest.fixture
def haircut(db):
    return system(
        "service.service.create",
        {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
    )


@pytest.fixture
def lucia(db):
    return system("customer.customer.create", {"name": "Lucía Pérez"})


@pytest.fixture
def bea(db):
    return system("staff.member.create", {"first_name": "Bea", "last_name": "Martín"})


@pytest.fixture
def ana(db):
    return system("staff.member.create", {"first_name": "Ana", "last_name": "López"})


@pytest.fixture
def grant(haircut, lucia):
    package = system(
        "service.package.create",
        {
            "name": "Bono 3 cortes",
            "max_uses": 3,
            "items": [{"service_id": str(haircut.id)}],
        },
    )
    return system(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id), "amount": 6000},
    )


def options(lucia, haircut, role="hub_employee"):
    return run(
        "service.grant.tender_options",
        {"customer_id": str(lucia.id), "service_id": str(haircut.id)},
        role,
    )


def sold(grant):
    [row] = run("service.grant.list", {"package_id": str(grant.package_id)}).rows
    return row


def movements(grant, permissions: set[str] | None = None):
    op = get("service.movement.list")
    ctx = ctx_for("hub_admin", permissions=permissions)
    return op(ctx, op.input.model_validate({"package_id": str(grant.package_id)})).rows


def till_check(haircut, grant, role="hub_employee", line=None, check=None):
    """A check with one haircut paid with the voucher, as the till leaves it; ``line`` and ``check`` add what the
    till lets say of the haircut's line and of the check (who serves them)."""
    order = run(
        "sale.order.open",
        {**(check or {}), "service_lines": [{"service_id": str(haircut.id), **(line or {})}]},
        role,
    )
    return run(
        "sale.order.apply_voucher",
        {
            "order_id": str(order.id),
            "line_id": str(order.lines[0].id),
            "grant_id": str(grant.id),
        },
        role,
    )


def test_a_session_held_at_the_till_counts_in_the_balance_and_in_the_options(
    haircut, lucia, grant
):
    [option] = options(lucia, haircut).rows
    assert (option.grant_id, option.remaining_before) == (grant.id, 3)
    till_check(haircut, grant)
    assert (sold(grant).used, sold(grant).remaining, sold(grant).can_void) == (
        1,
        2,
        False,
    )
    [option] = options(lucia, haircut).rows
    assert (option.used, option.remaining_before, option.remaining_after) == (1, 2, 1)
    [movement] = movements(grant)
    assert (movement.kind, movement.uses_delta, movement.service_name) == (
        "held",
        -1,
        "Haircut",
    )


def test_a_voucher_whose_session_is_held_at_the_till_is_not_voided(haircut, grant):
    till_check(haircut, grant)
    with pytest.raises(Conflict) as refusal:
        run("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"})
    assert refusal.value.code == "service.grant_in_use"


def test_the_whole_life_of_a_session_of_the_till_in_the_movements(
    haircut, lucia, grant
):
    order = till_check(haircut, grant)
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "svc-life-0001",
            "order_id": str(order.id),
            "customer_id": str(lucia.id),
        },
        "hub_employee",
    )
    [movement] = movements(grant)
    assert (movement.kind, movement.sale_id, movement.uses_delta) == (
        "consumed",
        sale.id,
        -1,
    )
    assert sold(grant).remaining == 2
    run(
        "sale.sale.void",
        {"sale_id": str(sale.id), "reason": "charged twice"},
        "hub_manager",
    )
    [movement] = movements(grant)
    assert (movement.kind, movement.reason, movement.uses_delta, movement.sale_number) == (
        "returned",
        "charged twice",
        0,
        sale.number,
    )
    assert (sold(grant).remaining, sold(grant).can_void) == (3, True)


def test_undoing_at_the_till_shows_the_session_released(haircut, grant):
    order = till_check(haircut, grant)
    run(
        "sale.order.remove_voucher",
        {"order_id": str(order.id), "line_id": str(order.lines[0].id)},
        "hub_employee",
    )
    [movement] = movements(grant)
    assert (movement.kind, movement.uses_delta) == ("released", 0)
    assert sold(grant).remaining == 3


def test_a_parked_check_forgotten_for_a_day_gives_its_session_back(
    haircut, lucia, grant
):
    # SERVICE-F25: the deadline frees the session at once; the hourly task only marks it.
    order = till_check(haircut, grant)
    line = order.lines[0]
    Redemption.objects.filter(order_line_id=line.id).update(
        hold_until=timezone.now() - dt.timedelta(minutes=1)
    )
    assert sold(grant).remaining == 3
    assert options(lucia, haircut).rows[0].remaining_before == 3
    assert (
        get("service.session.expire")(
            system_context(A), get("service.session.expire").input()
        ).expired
        == 1
    )
    [movement] = movements(grant)
    assert movement.kind == "expired"
    # Back at the check, charging it is refused until the voucher is applied again.
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.sale.complete",
            {
                "idempotency_key": "svc-park-0001",
                "order_id": str(order.id),
                "customer_id": str(lucia.id),
            },
        )
    assert refusal.value.code == "service.hold_lost"
    order = run(
        "sale.order.remove_voucher",
        {"order_id": str(order.id), "line_id": str(line.id)},
    )
    run(
        "sale.order.apply_voucher",
        {"order_id": str(order.id), "line_id": str(line.id), "grant_id": str(grant.id)},
    )
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "svc-park-0002",
            "order_id": str(order.id),
            "customer_id": str(lucia.id),
        },
    )
    assert sold(grant).remaining == 2


def test_a_refund_gives_the_session_back_and_the_movement_names_its_document(
    haircut, lucia, grant
):
    order = till_check(haircut, grant)
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "svc-ref-00001",
            "order_id": str(order.id),
            "customer_id": str(lucia.id),
        },
    )
    refund = run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "did not come",
            "allocations": [],
            "lines": [{"line_id": str(sale.lines[0].id)}],
        },
        "hub_manager",
    )
    session = Redemption.objects.get(order_line_id=order.lines[0].id)
    assert (session.status, session.return_reference, session.ended_by) == (
        "returned",
        refund.refund_id,
        "tester",
    )
    assert sold(grant).remaining == 3


def test_the_last_session_spent_at_the_till_leaves_no_option(haircut, lucia):
    package = system(
        "service.package.create",
        {"name": "Bono 1", "max_uses": 1, "items": [{"service_id": str(haircut.id)}]},
    )
    single = system(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id)},
    )
    till_check(haircut, single)
    assert options(lucia, haircut).rows == []
    with pytest.raises(Conflict) as refusal:
        till_check(haircut, single)
    assert refusal.value.code == "service.grant_no_uses_left"


def charge(order, lucia, key: str):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "order_id": str(order.id), "customer_id": str(lucia.id)},
        "hub_employee",
    )


def said_of_the_sale(movement) -> tuple:
    return (movement.sale_id, movement.sale_number, movement.member_id, movement.member_name)


def test_a_session_charged_at_the_till_names_its_sale_by_number_and_who_served_its_line(
    haircut, lucia, grant, ana, bea
):
    # The sale as Sales names it (its id says nothing to a person) and the professional of the line that spent it,
    # before the one who serves the check.
    order = till_check(haircut, grant, line={"staff_id": str(bea.id)}, check={"staff_id": str(ana.id)})
    sale = charge(order, lucia, "svc-num-00001")
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (sale.id, sale.number, bea.id, "Bea Martín")


def test_a_line_that_says_nobody_is_of_whoever_serves_the_check(haircut, lucia, grant, ana):
    order = till_check(haircut, grant, check={"staff_id": str(ana.id)})
    sale = charge(order, lucia, "svc-num-00002")
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (sale.id, sale.number, ana.id, "Ana López")


def test_a_sale_nobody_served_names_only_its_number(haircut, lucia, grant):
    sale = charge(till_check(haircut, grant), lucia, "svc-num-00003")
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (sale.id, sale.number, None, None)


def test_whoever_may_not_see_sales_reads_the_movement_without_its_sale(haircut, lucia, grant, bea):
    sale = charge(till_check(haircut, grant, line={"staff_id": str(bea.id)}), lucia, "svc-num-00004")
    allowed = permissions_for_role(all_live_app_configs(), "hub_admin") - {"sale.view_sale"}
    [movement] = movements(grant, allowed)
    assert said_of_the_sale(movement) == (sale.id, None, None, None)


def test_a_sale_sales_does_not_find_for_the_reader_is_not_named(haircut, lucia, grant):
    # Sales answers «does not exist» as well for a sale the reader may not see (someone else's, to an employee).
    charge(till_check(haircut, grant), lucia, "svc-num-00005")
    unknown = uuid7()
    Redemption.objects.update(sale_id=unknown)
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (unknown, None, None, None)


def test_with_sales_off_the_movements_still_read_without_the_sale(haircut, lucia, grant, bea, monkeypatch):
    sale = charge(till_check(haircut, grant, line={"staff_id": str(bea.id)}), lucia, "svc-num-00006")
    for name in [name for name in registry if name.startswith("sale.")]:
        monkeypatch.delitem(registry, name)
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (sale.id, None, None, None)


def test_a_session_spent_outside_the_till_on_a_sale_keeps_the_professional_it_said(haircut, lucia, grant, ana, bea):
    # Spent by hand saying its sale and who did it: the sale's check is served by someone else, and the session
    # still says its own professional, id and name.
    other = run("sale.order.open", {"staff_id": str(ana.id), "service_lines": [{"service_id": str(haircut.id)}]}, "hub_employee")
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "svc-num-00007", "order_id": str(other.id), "payments": [{"method": "card"}]},
        "hub_employee",
    )
    system("service.grant.redeem", {"id": str(grant.id), "member_id": str(bea.id), "sale_id": str(sale.id)})
    [movement] = movements(grant)
    assert said_of_the_sale(movement) == (sale.id, sale.number, bea.id, "Bea Martín")
