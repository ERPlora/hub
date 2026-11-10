"""Fixtures of the flow tests: contexts per role and scope, a frozen clock, a raw DSN, and builders of
the data a test starts from (straight to the models: the operations are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist. Other apps are always the real ones (task, customer, sale…), never a double.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")
MADRID = dt.timezone(dt.timedelta(hours=2))


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
    language: str = "en",
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    Owner and admin get every permission (``base.permissions.FULL_ACCESS_ROLES``); the others what each
    app's ``role_permissions`` gives them. ``permissions`` replaces them for a combination no role has.
    """
    if permissions is None:
        configs = all_live_app_configs()
        if role in ("hub_owner", "hub_admin"):
            permissions = {p for config in configs for p in config.permissions}
        else:
            permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data=None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` (a dict or its input schema) as ``ctx`` (an admin by default)."""
    op = get(name)
    payload = (
        data if isinstance(data, op.input) else op.input.model_validate(data or {})
    )
    return op(ctx or ctx_for(), payload)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def no_pauses(monkeypatch):
    """The assistant's door retries at once."""
    from apps.flow import gateway

    monkeypatch.setattr(gateway, "PAUSES", (0, 0))


@pytest.fixture
def worker(monkeypatch, django_capture_on_commit_callbacks):
    """One pass of the outbox relay, as the worker runs it every tick (base.relay); ``worker.request`` runs an operation
    as a request does, with what its COMMIT leaves for after it."""
    from django.db.backends.base.base import BaseDatabaseWrapper

    from base import relay

    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def tick():
        with django_capture_on_commit_callbacks(execute=True):
            return relay.run(timezone.now())

    def request(name, data, ctx=None):
        with django_capture_on_commit_callbacks(execute=True):
            return run(name, data, ctx)

    tick.request = request
    return tick


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.ADMIN, first_name: str = ""):
        user = get_user_model().objects.create_user(username=username, password="pw", first_name=first_name)
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def clock(monkeypatch):
    """``clock(instant)`` freezes ``timezone.now`` at ``instant`` (no real clock in these tests)."""

    def freeze(instant: dt.datetime) -> dt.datetime:
        monkeypatch.setattr(timezone, "now", lambda: instant)
        return instant

    return freeze


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


# The other system of «Call another system» (FLOW-F27): a real local HTTPS server.


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from .local_https import start

    yield from start(tmp_path_factory.mktemp("tls"))


@pytest.fixture
def trusted(settings, server):
    """The local server is trusted as a test's other system: its addresses and its certificate. Without
    this, the server is the machine itself, and a call to it is blocked."""
    from .local_https import Handler

    settings.FLOW_HTTP_TRUSTED_ADDRESSES = ["127.0.0.1", "::1"]
    settings.FLOW_HTTP_CA_BUNDLE = server["ca"]
    Handler.seen.clear()
    return f"https://localhost:{server['port']}"


# Builders

TASK_STEP = {
    "id": "s1",
    "kind": "command",
    "operation": "task.task.create",
    "params": {"title": "Welcome the new customer"},
}


def make_flow(name: str = "Welcome", **fields):
    """A flow straight in the table: by default on ``customer.customer.created``, creating a task."""
    from apps.flow.models import Flow

    fields.setdefault("trigger_kind", Flow.Trigger.EVENT)
    if fields["trigger_kind"] == Flow.Trigger.EVENT:
        fields.setdefault("trigger_event", "customer.customer.created")
    fields.setdefault("steps", [dict(TASK_STEP)])
    fields.setdefault("grants", ["task.task.create"])
    fields.setdefault("enabled", True)
    return Flow.objects.create(name=name, **fields)


def due_daily_flow(monkeypatch):
    """A flow every day at 09:00 whose 09:00 has not fired, with the clock at 12:00 of 2026-10-15 in Madrid."""
    from zoneinfo import ZoneInfo

    from apps.flow.models import Flow

    madrid = ZoneInfo("Europe/Madrid")
    now = dt.datetime(2026, 10, 15, 12, 0, tzinfo=madrid)
    monkeypatch.setattr(timezone, "now", lambda: now)
    return make_flow(
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
        next_fire_at=dt.datetime(2026, 10, 15, 9, 0, tzinfo=madrid),
    )


def make_run(flow, **fields):
    """A run of ``flow`` straight in the table, finished well unless told otherwise."""
    from apps.flow.models import FlowRun

    fields.setdefault("trigger_kind", flow.trigger_kind)
    fields.setdefault("trigger_key", f"test:{FlowRun.objects.count()}")
    fields.setdefault("status", FlowRun.Status.SUCCEEDED)
    fields.setdefault("definition", {"steps": flow.steps})
    fields.setdefault("flow_version", flow.version)
    return FlowRun.objects.create(flow=flow, **fields)


def make_draft(name: str = "Call who did not come", **fields):
    from apps.flow.models import Draft

    fields.setdefault(
        "definition",
        {"trigger": {"kind": "manual"}, "steps": [dict(TASK_STEP)]},
    )
    return Draft.objects.create(name=name, **fields)
