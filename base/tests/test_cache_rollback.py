"""Guardrail 10, «caché y avisos tras el COMMIT» (PLAN-DB §14.7; plan 2026-10-22-fase-2-tenencia §2.10).

A write of a datum the cache keeps forgets its key after its COMMIT, and only then is anybody told; a rollback leaves
the key as it was and tells nobody. The real case: turning an app off (``base.app.disable``) forgets the business's
apps off (``base.activation``, the cache's ``base.apps_off:{<host>}``) with ``live.operations.on_commit``, on the
operation's alias: in a hub with its own database that is the hub's, never control's (``default``), where a callback
would run at once, also after the hub's rollback.
"""

import pytest
from django.core.cache import cache
from django.db import transaction
from live.context import OperationContext, Scope
from live.operations import get

from base import activation
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

#: What another process kept of the business's apps off before the change.
KEPT = ["kept-before-the-change"]


class Abandoned(Exception):
    """What makes the change roll back, after the operation ran."""


def disable(hub, app: str) -> None:
    op = get("base.app.disable")
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}))
    op(ctx, op.input.model_validate({"app": app}))


def notices(sent: dict[str, list[str]]) -> list[str]:
    return [statement for statements in sent.values() for statement in statements if "pg_notify" in statement]


def test_a_rolled_back_change_keeps_the_cached_key_and_tells_nobody(hub_a, django_capture_on_commit_callbacks):
    key = activation.off_apps_key(hub_a.slug)
    cache.set(key, KEPT, 60)

    with (
        django_capture_on_commit_callbacks(using=hubs.HUB_A_ALIAS, execute=True) as on_the_hub,
        django_capture_on_commit_callbacks(execute=True) as on_control,
        hubs.watched() as sent,
    ):
        with pytest.raises(Abandoned), use_hub(hub_a), transaction.atomic(using=hubs.HUB_A_ALIAS):
            disable(hub_a, "website")
            raise Abandoned

    assert (on_the_hub, on_control) == ([], [])
    assert cache.get(key) == KEPT
    assert notices(sent) == []


def test_the_same_change_committed_forgets_the_key_and_tells_after_its_commit(
    hub_a, django_capture_on_commit_callbacks
):
    key = activation.off_apps_key(hub_a.slug)
    cache.set(key, KEPT, 60)

    with hubs.watched() as sent:
        with (
            django_capture_on_commit_callbacks(using=hubs.HUB_A_ALIAS) as on_the_hub,
            django_capture_on_commit_callbacks() as on_control,
        ):
            with use_hub(hub_a):
                disable(hub_a, "website")
        # Before its COMMIT nothing is forgotten and nobody is told.
        assert cache.get(key) == KEPT
        assert notices(sent) == []

        with use_hub(hub_a):  # the hub's COMMIT
            for callback in on_the_hub:
                callback()

    assert on_control == []
    assert cache.get(key) is None
    assert notices(sent) != []
