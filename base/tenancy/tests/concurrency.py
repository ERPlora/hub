"""Several sessions of the business at work at once, as several devices: each call in its own thread and session with
real row locks, and the platform staff's «Delete» in the Hub admin while another session writes."""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client

from base.tenancy import context, limits
from base.tenancy.connections import close_this_threads_connections
from base.tenancy.tests import hubs
from base.tenancy.tests.business import A

#: A plan of erplora.com with room for several sessions of a business at once: Free's lets one transaction in at a time,
#: so a second session would queue for its turn (or get 503 ``base.hub_busy``), never meet the first at a row's lock.
WITH_ROOM = {"slug": "standard", "max_db_connections": 6, "statement_timeout_seconds": 15}
#: How long a session waits for another one to queue behind its lock.
WAIT_LIMIT = 10
#: Where the platform's staff open the Hub admin.
PLATFORM_HOST = "hubs.localhost"
#: How the platform staff delete: from the row's delete page, or with the list's «Delete selected».
HOW = ["page", "list"]


@pytest.fixture
def plan_with_room(hub_a, monkeypatch):
    """Business A on :data:`WITH_ROOM`, read by limiters of this test alone: the next test finds its hub's limits as
    they were."""
    monkeypatch.setattr(limits, "_limiters", {})
    hub_a.state, hub_a.state_version = {"plan": WITH_ROOM}, hub_a.state_version + 1
    hub_a.save(update_fields=["state", "state_version"])
    limits.configure(hubs.HUB_A_ALIAS, hub_a)


def in_a_thread(call, outcomes: list, index: int = 0) -> threading.Thread:
    """A thread that runs ``call`` in the business at work and leaves its outcome at ``outcomes[index]`` (an error
    raised, a 500 included, is the outcome), with sessions of its own that it closes when it ends."""
    active = context.current()

    def target():
        try:
            with context.use_again(active):
                outcomes[index] = call()
        except Exception as error:  # reported to the test
            outcomes[index] = error
        finally:
            close_this_threads_connections()

    return threading.Thread(target=target)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def released(call):
        barrier.wait(5)
        return call()

    threads = [in_a_thread(lambda call=call: released(call), results, i) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def waited_for() -> bool:
    """Whether another session waits for a lock this one holds."""
    with connections[context.current_alias()].cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pg_backend_pid() = ANY (pg_blocking_pids(pid)))"
        )
        return cursor.fetchone()[0]


@pytest.fixture
def hub_staff(db) -> Client:
    """The platform staff, signed in to the Hub admin with business A chosen."""
    staff = get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")
    client = Client()
    client.force_login(staff)
    assert client.get(f"/admin/hub/{A.key}/", HTTP_HOST=PLATFORM_HOST).status_code == 302
    return client


def admin_delete(client: Client, how: str, *targets):
    """The Hub admin's «Delete» of ``targets`` (one for its page), ``how`` it says (see :data:`HOW`); calling it
    returns the answer."""
    meta = type(targets[0])._meta
    changelist = f"/admin/{meta.app_label}/{meta.model_name}/"
    if how == "page":
        [target] = targets
        url, data = f"{changelist}{target.pk}/delete/", {"post": "yes"}
    else:
        url, data = changelist, {
            "action": "delete_selected",
            "_selected_action": [str(target.pk) for target in targets],
            "post": "yes",
        }
    return lambda: client.post(url, data, HTTP_HOST=PLATFORM_HOST, HTTP_ACCEPT_LANGUAGE="en")


@contextmanager
def meanwhile(when: Callable[[str], bool], call, *, first: bool = False):
    """Runs ``call`` in another session right after the first statement of this one for which ``when`` holds, or
    right before it if ``first``; this one goes on once ``call`` waits for what it holds (or has ended). Yields its
    outcome (an error raised, a 500 included, is the outcome)."""
    outcome: list = [None]
    thread = in_a_thread(call, outcome)

    def let_it_run():
        thread.start()
        deadline = time.monotonic() + WAIT_LIMIT
        while thread.is_alive() and not waited_for() and time.monotonic() < deadline:
            time.sleep(0.02)

    def wrapper(execute, sql, params, many, executing):
        starts = thread.ident is None and when(sql)
        if starts and first:
            let_it_run()
        result = execute(sql, params, many, executing)
        if starts and not first:
            let_it_run()
        return result

    try:
        with connections[context.current_alias()].execute_wrapper(wrapper):
            yield outcome
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "this session never ran the statement the call waits for"
