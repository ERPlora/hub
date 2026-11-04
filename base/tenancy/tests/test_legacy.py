"""The suite's stand-in for the worker's pass (:func:`base.tenancy.tests.legacy.worker_pass`, hub#625).

A test that runs the worker's loop on the suite's businesses gets their scheduled tasks as ``base.worker._serve_hub``
runs them for a business with its own database: on its own scope, so nothing of an app off there runs. On the worker's
fixed scope (``WORKER_SCOPE_SLUG``) such a test would measure something production no longer does.
"""

import datetime as dt

import pytest
from django.conf import settings
from django.db.backends.base.base import BaseDatabaseWrapper
from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base import scheduler
from base.models import TaskSchedule
from base.tenancy.tests import legacy

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
NOW = dt.datetime(2026, 11, 4, 10, 0, tzinfo=dt.UTC)
OWNER = OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}), language="en")


@pytest.fixture
def due(monkeypatch):
    """Every task that runs each minute is due at NOW."""
    # The pass releases its connections after each task; this test's transaction is on one of them.
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    scheduler.sync(NOW - dt.timedelta(minutes=10))


def test_the_tasks_due_run_on_the_scope_of_the_business_never_on_the_worker_s_fixed_one(due, monkeypatch):
    ran: list[tuple[str, Scope]] = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope: ran.append((name, scope)))

    legacy.worker_pass(NOW)

    assert ("flow.run.resume_due", A) in ran
    assert {scope for _, scope in ran} == {A}
    assert settings.WORKER_SCOPE_SLUG != A.key


def test_a_task_of_an_app_the_business_turned_off_does_not_run(due):
    disable = get_operation("base.app.disable")
    disable(OWNER, disable.input.model_validate({"app": "flow"}))

    legacy.worker_pass(NOW)

    assert TaskSchedule.objects.get(app_label="flow", name="resume_due").last_run is None
    assert TaskSchedule.objects.get(app_label="whatsapp_inbox", name="resume_deliveries").last_run == NOW
