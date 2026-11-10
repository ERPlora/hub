"""Retired phase-1 seams never change the active hub's behavior (hub#1053)."""

import inspect

import pytest
from live.context import OperationContext, Scope
from live.operations import get
from ninja import Schema

from base import activation, outbound
from base.models import AppActivation
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_outbound import as_system, command

ADMIN = "base.administer_hub"


def run(name, *permissions, scope, **data):
    op = get(name)
    ctx = OperationContext(scope=scope, actor="ana", permissions=frozenset(permissions))
    return op(ctx, op.input.model_validate(data)).model_dump(mode="json")

pytestmark = [
    pytest.mark.django_db(databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]


def test_the_worker_scope_is_not_mistaken_for_the_platform(hub_a, hub_b, settings):
    settings.WORKER_SCOPE_SLUG = hub_a.slug
    settings.PLATFORM_HUB_SLUG = "erplora"
    with use_hub(hub_a):
        AppActivation.objects.filter(host=hub_a.slug, app="task").update(state="off")
        assert activation.is_platform(Scope("host", hub_a.slug)) is False
        assert activation.off_apps(Scope("host", hub_a.slug)) == frozenset({"task"})
    with use_hub(hub_b):
        assert activation.is_platform(Scope("host", settings.PLATFORM_HUB_SLUG)) is True


def test_after_commit_has_no_legacy_scope_parameter(hub_a, django_capture_on_commit_callbacks):
    assert "scope" not in inspect.signature(outbound.after_commit).parameters
    with use_hub(hub_a) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
        result = command(
            lambda ctx, data: outbound.after_commit(lambda: None) or {"count": 1}
        )(as_system(Scope("host", hub_a.slug)), Schema())
    assert result.count == 1


def test_system_status_has_no_shared_database_state(hub_a):
    with use_hub(hub_a):
        answer = run("base.system.status", ADMIN, scope=Scope("host", hub_a.slug))
    assert "shared_database" not in answer
    assert set(answer) == {"version", "released_at"}
