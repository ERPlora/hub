"""What a change of an app's state does at its COMMIT and while it holds the business's rows: the gate's cache it
forgets, the change it tells to its own business only, and two changes at once.
"""

import psycopg
import pytest
from django.db import connections
from live.errors import AppInactive
from live.models import OutboxEvent
from live.operations import get

from apps.flow.tests.test_relay import heard, listen
from apps.sale.tests.conftest import db_dsn
from base import activation, apps_on, events
from base.activation import ON, Activation
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.business import HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import at_once, in_a_thread, meanwhile, plan_with_room
from base.tests.test_app_activation import app_list, born_off, ctx, disable, enable, rows, set_rows, with_limit
from base.tests.test_app_activation_off import put_photo, registered_a

#: Business A entered for every test with the database, room for two of its sessions at once, control's LISTEN and
#: business A as the SaaS registered it.
__all__ = ["db_dsn", "in_business_a", "listen", "plan_with_room", "registered_a"]


# ── The gate's cache: one read per business, forgotten at the COMMIT of a change ───────────────────────────


def task_list_as(scope=A, hub=None):
    """``task.task.list`` in ``scope``'s business, entering ``hub``'s database when it is not the one at work."""
    op = get("task.task.list")
    if hub is None:
        return op(ctx(scope=scope), op.input())
    with use_hub(hub):
        return op(ctx(scope=scope), op.input())


def activation_reads(captured):
    return [query["sql"] for query in captured.captured_queries if "base_appactivation" in query["sql"]]


@HUB_DB
def test_with_the_cache_warm_the_operations_read_no_row():
    from django.test.utils import CaptureQueriesContext

    set_rows(task="on*", staff="on")
    task_list_as()  # the first one reads the rows once

    with CaptureQueriesContext(connections[current_alias()]) as captured:  # the business's own database
        for _ in range(3):
            task_list_as()
            assert "task" in apps_on.active_apps(A)
            get("base.session.me")(ctx(), get("base.session.me").input())

    assert activation_reads(captured) == []


@HUB_DB
def test_each_business_has_its_own_entry(hub_b):
    from django.core.cache import cache

    set_rows(A.key, staff="on*")
    with pytest.raises(AppInactive):
        task_list_as(A)
    task_list_as(B, hub_b)

    assert "task" in cache.get(activation.OFF_APPS_CACHE + A.key)
    assert cache.get(activation.OFF_APPS_CACHE + B.key) == []


@HUB_DB_COMMITTED
def test_turned_off_and_committed_the_next_operation_is_refused_at_once():
    task_list_as()  # warm: on

    disable("task")
    with pytest.raises(AppInactive):
        task_list_as()

    enable("task")
    assert task_list_as().model_dump()["rows"] == []


@HUB_DB
def test_the_commit_forgets_what_another_process_cached_meanwhile(django_capture_on_commit_callbacks):
    from django.core.cache import cache

    set_rows(task="on*", staff="on")
    with django_capture_on_commit_callbacks(using=current_alias()) as callbacks:
        disable("task")
    # Before the COMMIT another process read the rows as they were, and kept them.
    cache.set(activation.OFF_APPS_CACHE + A.key, [], 60)

    for callback in callbacks:
        callback()

    with pytest.raises(AppInactive):
        task_list_as()


@HUB_DB
def test_inside_a_change_nothing_is_kept_before_its_commit(client, registered_a):
    """What a change reads of its own rows (the photo's block it applies, the gate of that sync) is not committed yet:
    it is never kept, or a rollback would leave the cache saying what never happened."""
    from django.core.cache import cache

    set_rows(staff="on*")
    put_photo(client, registered_a, 3, status="active", verifactu={"representation": {"status": "approved", "updated_at": "2026-10-15T10:00:00Z", "reason": ""}})
    cache.delete(activation.OFF_APPS_CACHE + A.key)

    enable("verifactu")

    assert cache.get(activation.OFF_APPS_CACHE + A.key) is None


@HUB_DB
def test_without_the_cache_the_gate_reads_the_rows(monkeypatch, caplog, hub_b):
    class Unreachable:
        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise ConnectionError("Valkey is down")

            return fail

    monkeypatch.setattr(activation, "cache", Unreachable())
    set_rows(staff="on*")

    with pytest.raises(AppInactive):
        task_list_as(A)
    task_list_as(B, hub_b)
    enable("task")
    assert task_list_as(A).model_dump()["rows"] == []
    assert "base.activation.cache_unavailable" in caplog.text


# ── After the COMMIT, to its own business only ──────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_turning_one_off_in_b_is_told_to_b_and_never_to_a(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    changes = (events.APP_DISABLED, events.APP_ENABLED)

    with use_hub(hub_b):
        disable("task", context=ctx(scope=B))
        enable("task", context=ctx(scope=B))
        written = set(OutboxEvent.objects.filter(name__in=changes).values_list("scope_kind", "scope_key", "name"))

    assert heard(on_b) == set(changes)
    assert heard(on_a, timeout=0.2) == set()
    assert written == {("host", B.key, name) for name in changes}
    assert not OutboxEvent.objects.filter(name__in=changes).exists()  # A's outbox


@HUB_DB_COMMITTED
def test_two_at_the_limit_at_once_turn_on_only_one(plan_with_room):
    """The rows of the business are locked while one turns an app on: two people at once cannot both pass the
    limit."""
    with_limit(A.key, 2)
    set_rows(task="on*", staff="on")

    outcomes = at_once(lambda: enable("website"), lambda: enable("flow"))

    assert sorted(o["state"] if isinstance(o, dict) else o.code for o in outcomes) == ["base.app_limit_reached", "on"]
    assert app_list()["enabled"] == 2


@HUB_DB_COMMITTED
def test_a_change_waits_while_another_holds_the_business_rows(plan_with_room):
    """What makes the limit hold with two people at once: a change locks every row of its business, the ones it does
    not touch too (a row held elsewhere, Tasks, holds a change of Website)."""
    with_limit(A.key, 20)
    set_rows(task="on*", staff="on")
    holder = psycopg.connect(**connections[current_alias()].get_connection_params())  # in the business's own database
    holder.execute("SELECT id FROM base_appactivation WHERE host = %s AND app = 'task' FOR UPDATE", [A.key])
    outcome: list = [None]
    thread = in_a_thread(lambda: enable("website"), outcome)
    thread.start()
    try:
        thread.join(0.7)
        assert thread.is_alive(), "the change did not wait for the business's rows"
    finally:
        holder.rollback()
        holder.close()
    thread.join(10)
    assert not thread.is_alive() and outcome[0]["state"] == "on"
    assert rows()["website"] == Activation(ON, True)


@HUB_DB_COMMITTED
def test_two_first_changes_at_once_write_the_business_down_once(plan_with_room):
    born_off()
    with meanwhile(lambda sql: sql.lstrip().startswith('INSERT INTO "base_appactivation"'), lambda: enable("flow")) as flow:
        assert enable("website")["state"] == "on"
    assert isinstance(flow[0], dict) and flow[0]["state"] == "on", flow
    now = rows()
    assert len(now) == len(activation.module_graph()) and now["website"] == now["flow"] == Activation(ON, True)
