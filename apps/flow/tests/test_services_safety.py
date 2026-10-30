"""What an automation may never do, and with what it acts (review 2026-10-15, items 1 and 2).

- An action that needs a person in front (``ai.risk == "high"``: voiding, refunding, erasing, sending to
  the tax agency…) is refused when the automation is saved, when it is granted and when it runs, with
  the stable code ``flow.high_risk``.
- A step acts with the permission of its own operation (and the read permissions of its app), never with
  every permission: an operation's own checks still apply (the old engine's «no elevation»).
- Whoever grants may only grant what they may do themselves.
"""

import pytest
from live.context import Scope
from live.errors import InvalidPayload, PermissionDenied
from live.operations import get

from apps.flow import services
from apps.flow.models import FlowRun
from apps.sale.models import Order

from .conftest import A, TASK_STEP, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

VOID = {"id": "s1", "kind": "command", "operation": "sale.order.void", "params": {"order_id": "input.order_id"}}


@pytest.fixture(autouse=True)
def without_cash_register(monkeypatch):
    monkeypatch.setattr("apps.sale.services.DRAWER_CHECK", "cash_register.session.not_installed")


@pytest.fixture
def check_with_a_line():
    """An open check with a coffee on it: voiding it is a manager's (``sale.void_sale``)."""
    from live.context import system_context

    run(
        "inventory.product.create",
        {"name": "Coffee", "sku": "COF", "price": 150, "tax_category_key": "restaurant.drink"},
        system_context(A),
    )
    return run("sale.order.open", {"lines": [{"product": "COF"}]}, system_context(A))


def test_saving_a_step_that_needs_a_person_is_refused_with_its_code():
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", {"steps": [VOID]})
    assert refused.value.code == "flow.high_risk"
    assert refused.value.fields == {
        "steps.0.operation": "«sale.order.void» needs a person in front: an automation cannot do it."
    }


def test_granting_what_needs_a_person_is_refused_with_its_code():
    flow = make_flow(grants=[])
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.grant", {"id": str(flow.id), "operations": ["task.task.create", "sale.order.void"]})
    assert refused.value.code == "flow.high_risk"
    assert set(refused.value.fields) == {"operations.1"}


def test_a_step_that_needs_a_person_is_refused_when_it_runs_even_if_it_slipped_in(check_with_a_line):
    # Written straight in the table, as an old row or a raw admin edit could leave it.
    flow = make_flow(trigger_kind="manual", steps=[VOID], grants=["sale.order.void"])
    result = run("flow.flow.run", {"id": str(flow.id), "input": {"order_id": str(check_with_a_line.id)}})
    assert (result.status, result.error_code) == ("failed", "flow.high_risk")
    assert Order.objects.get(pk=check_with_a_line.id).status != "voided"


def test_a_step_acts_only_with_its_own_permission_so_an_operation_s_checks_still_apply(monkeypatch, check_with_a_line):
    # Even were voiding not high risk, the step holds «sale.add_sale» (its operation's) and the reads of
    # Sales, never «sale.void_sale»: a check with something on it stays as it is.
    op = get("sale.order.void")
    monkeypatch.setattr(op, "ai", {**op.ai, "risk": "normal"})
    flow = make_flow(trigger_kind="manual", steps=[VOID], grants=["sale.order.void"])
    result = run("flow.flow.run", {"id": str(flow.id), "input": {"order_id": str(check_with_a_line.id)}})
    assert (result.status, result.error_code) == ("failed", "permission_denied")
    assert Order.objects.get(pk=check_with_a_line.id).status != "voided"


def test_the_step_context_holds_its_operation_s_permission_and_its_app_s_reads():
    flow = make_flow()
    started = FlowRun.objects.create(flow=flow, flow_version=1, trigger_kind="manual", trigger_key="k")
    ctx = services._step_context(ctx_for(scope=Scope("host", "a")), started, flow, get("task.task.create"))
    assert ctx.permissions == frozenset({"task.add", "task.view", "task.view_all"})
    assert ctx.actor == f"flow_run:{started.id}"
    assert not ctx.has("task.delete") and not ctx.has("customer.view")


def test_only_what_the_caller_may_do_is_granted():
    flow = make_flow(grants=[])
    only_flow = ctx_for(permissions={"flow.view", "flow.manage"})
    with pytest.raises(PermissionDenied) as refused:
        run("flow.flow.grant", {"id": str(flow.id), "operations": ["task.task.create"]}, only_flow)
    assert refused.value.fields == {
        "operations.0": "You cannot allow what you may not do yourself: «task.task.create»."
    }
    with_tasks = ctx_for(permissions={"flow.view", "flow.manage", "task.add"})
    assert run("flow.flow.grant", {"id": str(flow.id), "operations": ["task.task.create"]}, with_tasks).grants == [
        "task.task.create"
    ]


def test_a_normal_step_still_runs_with_its_narrow_permission():
    flow = make_flow(trigger_kind="manual", steps=[TASK_STEP])
    assert run("flow.flow.run", {"id": str(flow.id)}).status == "succeeded"


def test_a_step_that_books_by_phone_still_holds_nothing_of_customers():
    # FIX-HUB-FLOW-STEP-RESERVATION-BY-PHONE-DENIED: booking finds or makes the guest's card by itself, the step
    # never gets Customers' rights: it can neither look a card up nor make one on its own.
    flow = make_flow(grants=["reservation.reservation.create"])
    started = FlowRun.objects.create(flow=flow, flow_version=1, trigger_kind="manual", trigger_key="k")
    ctx = services._step_context(ctx_for(scope=A), started, flow, get("reservation.reservation.create"))
    assert not ctx.has("customer.view") and not ctx.has("customer.manage")
    with pytest.raises(PermissionDenied):
        run("customer.customer.by_phone", {"phone": "600111222"}, ctx)
    with pytest.raises(PermissionDenied):
        run("customer.customer.create", {"name": "Ana García", "phone": "600111222"}, ctx)
