"""FIX-SCHEDULED-TASK-LIVE-NOTICE-WRONG-CHANNEL: the live notice of what a scheduled task did goes on the channel of
the hub it belongs to, never on the worker's fixed scope (``WORKER_SCOPE_SLUG``, the platform hub in production).

In a hub with its own database the worker runs its tasks in that database and on its scope (``base.worker._hubs``,
review of hub#471 C1; S3): a schedule of Flows firing at its time is told to that hub's live queries (its History open on
a screen re-runs without reloading). Real databases: the session's ``hub_a``, committed (``transaction=True``).
"""

import datetime as dt

import pytest
from django.conf import settings
from django.utils import timezone
from live import operations as live_operations

from base import worker
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Hub

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]


@pytest.fixture
def no_test_fallback(monkeypatch):
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.fixture(autouse=True)
def nothing_synced_yet(monkeypatch):
    monkeypatch.setattr(worker, "_synced", set())
    monkeypatch.setattr(worker, "_next_hub", None)


@pytest.fixture
def told(monkeypatch):
    """Every live notice sent after a COMMIT: ``(scope key, event names)``."""
    sent: list[tuple[str, list[str]]] = []
    real = live_operations.notify_hook

    def hook(scope, names):
        sent.append((scope.key, list(names)))
        if real is not None:
            real(scope, names)

    monkeypatch.setattr(live_operations, "notify_hook", hook)
    return sent


def test_a_flow_schedule_fired_by_the_worker_is_told_on_its_hubs_channel(hub_a, told):
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
    with use_control():
        worker._hubs(now)  # its schedule written in its database, each task due at its next time

    with use_control():
        worker._hubs(now + dt.timedelta(days=2))

    flow_notices = [(key, names) for key, names in told if any(name.startswith("flow.") for name in names)]
    assert flow_notices, f"the fired schedule was told to nobody: {told}"
    assert {key for key, _ in flow_notices} == {hub_a.slug}
    assert settings.WORKER_SCOPE_SLUG not in {key for key, _ in told}
