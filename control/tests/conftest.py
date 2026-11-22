"""Fixtures shared by control's tests."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext
from live.models import OutboxEvent

from base.registry import REGISTRY_SCOPE
from base.tenancy import credentials
from base.tenancy.context import use_control
from base.tenancy.tests.concurrency import hub_staff
from control.models import Cluster, Hub

__all__ = [
    "SERVICES_MARKS",
    "a_cluster",
    "a_ready_hub",
    "admin_ctx",
    "as_actor",
    "events",
    "hub_staff",
    "nothing_cached",
    "person",
    "small",
]

#: The marks of the tests of control's services: they use the database, and no secret read before them is kept.
SERVICES_MARKS = [pytest.mark.django_db, pytest.mark.usefixtures("nothing_cached")]


@pytest.fixture
def admin_ctx():
    """A platform admin (staff and superuser) acting on the registry, as the Hub admin's actions do."""
    root = get_user_model().objects.create_user(username="root", password="pw", is_staff=True, is_superuser=True)
    return OperationContext(scope=REGISTRY_SCOPE, actor=root, permissions=frozenset(), language="en")


def events(name: str) -> list[dict]:
    """The payloads of the events ``name`` in control's outbox, oldest first: a platform operation records them there,
    under the registry's scope, whatever business is at work."""
    with use_control():
        rows = list(OutboxEvent.objects.filter(name=name).order_by("created_at"))
    assert {(row.scope_kind, row.scope_key) for row in rows} <= {(REGISTRY_SCOPE.kind, REGISTRY_SCOPE.key)}, name
    return [row.payload for row in rows]


@pytest.fixture
def nothing_cached():
    credentials.forget()
    yield
    credentials.forget()


def person(username: str, **flags):
    return get_user_model().objects.create_user(username=username, password="pw", **flags)


def as_actor(actor) -> OperationContext:
    return OperationContext(scope=REGISTRY_SCOPE, actor=actor, permissions=frozenset(), language="en")


def a_cluster(**fields) -> Cluster:
    return Cluster.objects.create(**({"name": "cluster-1", "host": "writer-1.example"} | fields))


@pytest.fixture
def small(monkeypatch):
    """The hub's database (or its copy) measures 5 MB on the server asked (``control.queries.measure``)."""
    from control import queries

    measured: list[tuple[object, list[str]]] = []

    def measure(cluster, names):
        measured.append((cluster, names))
        return {name: 5 * 1024 * 1024 for name in names}

    monkeypatch.setattr(queries, "measure", measure)
    return measured


def a_ready_hub(**fields) -> Hub:
    row = {"slug": "acme", "status": Hub.Status.READY, "db_name": f"hub_{uuid.uuid7().hex}"}
    return Hub.objects.create(**(row | fields))
