"""Several sessions of business A at once, as several devices work: each call in its own thread and session of the
business at work, a session that goes on once another waits for the lock it holds, and the platform staff's «Delete»
in the Hub admin."""

import time

import pytest
from django.apps import apps
from django.db import connections
from live.operations import atomic

from base.tenancy import context, limits
from base.tenancy.tests import hubs
from base.tenancy.tests.business import HUB_DB_COMMITTED, in_business_a
from base.tenancy.tests.concurrency import (
    HOW,
    PLATFORM_HOST,
    WAIT_LIMIT,
    admin_delete,
    at_once,
    hub_staff,
    meanwhile,
    plan_with_room,
    waited_for,
)

pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]

MARKED = "SELECT 'marked'"
LOCK = "SELECT 1 FROM base_hub_identity FOR UPDATE"


def cursor():
    return connections[context.current_alias()].cursor()


def session() -> tuple[str, int]:
    with cursor() as opened:
        opened.execute("SELECT pg_backend_pid()")
        return context.current_alias(), opened.fetchone()[0]


def test_each_call_runs_in_its_own_session_of_the_business_at_work():
    results = at_once(session, session, session)
    assert {alias for alias, _ in results} == {hubs.HUB_A_ALIAS}
    assert len({pid for _, pid in results}) == 3


def test_a_call_that_fails_hands_its_error_to_the_test():
    def refused():
        raise ValueError("refused")

    [result] = at_once(refused)
    assert isinstance(result, ValueError)


def test_business_a_has_room_for_several_transactions_at_once():
    assert limits.limiter_for(hubs.HUB_A_ALIAS).limits.max_transactions > 1


def order_of_the_call_and_the_marked_statement(*, first: bool) -> list[str]:
    order: list[str] = []

    def seen(execute, sql, params, many, executing):
        if sql == MARKED:
            order.append("statement")
        return execute(sql, params, many, executing)

    with meanwhile(lambda sql: sql == MARKED, lambda: order.append("call"), first=first):
        with connections[context.current_alias()].execute_wrapper(seen), cursor() as opened:
            opened.execute(MARKED)
    return order


def test_meanwhile_runs_the_call_right_after_the_statement_it_waits_for():
    assert order_of_the_call_and_the_marked_statement(first=False) == ["statement", "call"]


def test_meanwhile_first_runs_the_call_right_before_the_statement_it_waits_for():
    assert order_of_the_call_and_the_marked_statement(first=True) == ["call", "statement"]


def test_meanwhile_goes_on_once_the_call_waits_for_the_lock_this_session_holds():
    def locks():
        with cursor() as opened:
            opened.execute(LOCK)
        return "locked"

    with meanwhile(lambda sql: sql == LOCK, locks) as outcome:
        with atomic(), cursor() as opened:
            started = time.monotonic()
            opened.execute(LOCK)
            assert time.monotonic() - started < WAIT_LIMIT
            assert waited_for()
            assert outcome == [None]
    assert outcome == ["locked"]


def test_the_hub_staff_work_in_the_hub_admin_with_business_a_chosen(hub_staff):
    assert hub_staff.get("/admin/customer/customer/", HTTP_HOST=PLATFORM_HOST).status_code == 200


@pytest.mark.parametrize("how", HOW)
def test_admin_delete_deletes_a_row_of_business_a_as_the_staff_would(hub_staff, how):
    customer = apps.get_model("customer", "Customer")
    card = customer.objects.create(name="Ana López")
    assert admin_delete(hub_staff, how, card)().status_code == 302
    assert not customer.objects.filter(pk=card.pk).exists()
