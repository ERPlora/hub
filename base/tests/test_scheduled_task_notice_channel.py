"""The live notice of what a scheduled task did goes on the channel of
the hub it belongs to, never on the worker's fixed scope (``WORKER_SCOPE_SLUG``, the platform hub in production).

In a hub with its own database the worker runs its tasks in that database and on its scope (``base.hub_visits``,
hub#471): a schedule of Flows firing at its time, or the carts Cart and checkout expires
(CART_CHECKOUT-F07), is told to that hub's live queries and to no other's (its History or its list of carts open on a
screen re-runs without reloading). Real databases: the session's ``hub_a`` and ``hub_b``, committed
(``transaction=True``).
"""

import datetime as dt

import pytest
from django.conf import settings
from django.utils import timezone
from live.live_registry import live_registry

from base import hub_visits
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models.hubs import Hub

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
]


@pytest.fixture(autouse=True)
def every_hub_in_one_pass(monkeypatch):
    # A loaded machine must not leave the second hub for a later tick than the test runs.
    monkeypatch.setattr(hub_visits, "HUB_PASS_SECONDS", 3600)


def tasks_run_by_the_worker(visits, now: dt.datetime) -> None:
    """Its first pass writes each hub's schedule, each task due at its next time; the next, days on, runs them."""
    with use_control():
        visits.serve(now)
    with use_control():
        visits.serve(now + dt.timedelta(days=2))


def told_to(told: list[tuple[str, list[str]]], event: str) -> set[str]:
    return {key for key, names in told if event in names}


def test_a_flow_schedule_fired_by_the_worker_is_told_on_its_hubs_channel(hub_a, told, worker_visits):
    from apps.flow.models import Flow

    now = timezone.now()
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        Flow.objects.create(
            name="Every day at noon",
            trigger_kind=Flow.Trigger.SCHEDULE,
            trigger_event="",
            schedule={"every": "day", "time": "12:00"},
            next_fire_at=now - dt.timedelta(minutes=1),  # due by the clock of the operation that fires it
            steps=[{"id": "s1", "kind": "command", "operation": "task.task.create", "params": {"title": "Open"}}],
            grants=["task.task.create"],
            enabled=True,
        )
    tasks_run_by_the_worker(worker_visits, now)

    flow_notices = [(key, names) for key, names in told if any(name.startswith("flow.") for name in names)]
    assert flow_notices, f"the fired schedule was told to nobody: {told}"
    assert {key for key, _ in flow_notices} == {hub_a.slug}
    assert settings.WORKER_SCOPE_SLUG not in {key for key, _ in told}


def test_carts_expired_by_the_worker_are_told_on_their_hubs_channel_and_no_other(hub_a, hub_b, told, worker_visits):
    # CART_CHECKOUT-F07: the list open in that business re-runs at once; the other's hears nothing.
    from apps.cart_checkout.events import CART_EXPIRED
    from apps.cart_checkout.models import Cart

    now = timezone.now()
    with use_hub(hub_b):
        overdue = Cart.objects.create(session_token="sess_overdue", expires_at=now - dt.timedelta(days=1))
    with use_hub(hub_a):
        still_on = Cart.objects.create(session_token="sess_still_on", expires_at=now + dt.timedelta(days=1))

    tasks_run_by_the_worker(worker_visits, now)

    with use_hub(hub_b):
        assert Cart.objects.get(pk=overdue.pk).status == Cart.Status.EXPIRED
    with use_hub(hub_a):
        assert Cart.objects.get(pk=still_on.pk).status == Cart.Status.ACTIVE
    assert told_to(told, CART_EXPIRED) == {hub_b.slug}
    assert "cart_checkout.cart.list" in live_registry.affected([CART_EXPIRED])
