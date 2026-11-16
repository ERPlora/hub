"""Fixtures shared by control's tests."""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext
from live.models import OutboxEvent

from base.registry import REGISTRY_SCOPE
from base.tenancy.context import use_control
from base.tenancy.tests.concurrency import hub_staff

__all__ = ["admin_ctx", "events", "hub_staff"]


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
