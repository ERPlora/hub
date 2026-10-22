"""``use_hub``, ``use_control`` and the database of an operation (PLAN-DB §4; plan 2026-10-22-fase-2-tenencia §4, 3).

The context lives in a ``ContextVar``: nested contexts restore the outer one, ``sync_to_async`` inherits it and a
thread of its own starts without it. Without a context, a hub's database is never guessed: ``HubContextMissing``.
Every test runs in a fresh ``contextvars.Context``, so nothing the suite sets around it leaks in.
"""

import contextvars
import threading
import uuid
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from live.context import OperationContext, Scope

from base.tenancy import context
from base.tenancy.context import HubContextMismatch, HubContextMissing

pytestmark = pytest.mark.usefixtures("no_test_fallback")


def shared_hub(slug: str):
    """A hub of phase 1: no database of its own (``db_name=""``), so its alias is control's."""
    return SimpleNamespace(id=uuid.uuid7(), slug=slug, db_name="")


def fresh(fn, *args):
    """Run ``fn`` in a context where nothing is set."""
    return contextvars.Context().run(fn, *args)


def ctx_of(kind: str, key: str) -> OperationContext:
    return OperationContext(scope=Scope(kind, key), actor="system", permissions=frozenset({"*"}))


def op(name: str = "demo.item.list"):
    return SimpleNamespace(name=name)


def test_without_a_context_there_is_no_alias():
    def probe():
        with pytest.raises(HubContextMissing):
            context.current_alias()
        with pytest.raises(HubContextMissing):
            context.current()

    fresh(probe)


def test_a_hub_of_the_shared_database_runs_on_control_until_it_has_its_own():
    a = shared_hub("a")

    def probe():
        with context.use_hub(a) as active:
            assert active.kind == context.HUB
            assert active.hub is a
            assert context.current_alias() == "default"
            assert context.current_hub() is a

    fresh(probe)


def test_nested_contexts_restore_the_outer_one_even_after_an_error():
    a, b = shared_hub("a"), shared_hub("b")

    def probe():
        with context.use_hub(a):
            with context.use_hub(b):
                assert context.current_hub() is b
            assert context.current_hub() is a
            with pytest.raises(ZeroDivisionError), context.use_control():
                raise ZeroDivisionError
            assert context.current_hub() is a
        with pytest.raises(HubContextMissing):
            context.current()

    fresh(probe)


def test_control_has_no_hub_and_its_alias_is_default():
    def probe():
        with context.use_control() as active:
            assert active.kind == context.CONTROL
            assert context.current_hub() is None
            assert context.current_alias() == "default"

    fresh(probe)


def test_the_shared_database_of_phase_one_is_default_without_a_hub():
    def probe():
        with context.use_shared_database() as active:
            assert active.kind == context.SHARED
            assert context.current_hub() is None
            assert context.current_alias() == "default"

    fresh(probe)


async def test_sync_to_async_inherits_the_context():
    a = shared_hub("a")
    with context.use_hub(a):
        assert await sync_to_async(context.current_hub)() is a


def test_a_thread_of_its_own_starts_without_one():
    a = shared_hub("a")
    seen = []

    def in_thread():
        try:
            context.current()
        except HubContextMissing as missing:
            seen.append(missing)

    def probe():
        with context.use_hub(a):
            thread = threading.Thread(target=in_thread)
            thread.start()
            thread.join()

    fresh(probe)
    assert len(seen) == 1


# ── The database of an operation (live's LIVE["operation_database"]) ──────────────────────────────────────────


def test_a_platform_operation_runs_on_control_from_anywhere():
    a = shared_hub("a")

    def probe():
        with context.operation_database(op("base.hub.register"), ctx_of("platform", "registry")) as alias:
            assert alias == "default"
            assert context.current().kind == context.CONTROL
        with context.use_hub(a):
            with context.operation_database(op("base.demo.expire"), ctx_of("platform", "registry")) as alias:
                assert context.current().kind == context.CONTROL
            assert context.current_hub() is a

    fresh(probe)


def test_a_hubs_operation_without_its_hub_is_refused():
    def probe():
        with pytest.raises(HubContextMissing):
            with context.operation_database(op(), ctx_of("host", "a")):
                pass
        with context.use_control(), pytest.raises(HubContextMissing):
            with context.operation_database(op(), ctx_of("host", "a")):
                pass

    fresh(probe)


def test_a_hubs_operation_runs_on_its_hubs_alias():
    a = shared_hub("a")

    def probe():
        with context.use_hub(a), context.operation_database(op(), ctx_of("host", "a")) as alias:
            assert alias == "default"
            assert context.current_hub() is a

    fresh(probe)


def test_an_operation_for_another_hub_never_runs_in_this_one():
    a = shared_hub("a")

    def probe():
        with context.use_hub(a), pytest.raises(HubContextMismatch, match="b"):
            with context.operation_database(op(), ctx_of("host", "b")):
                pass

    fresh(probe)


def test_the_shared_database_runs_any_hubs_operation_on_default():
    def probe():
        with context.use_shared_database():
            for key in ("a", "b"):
                with context.operation_database(op(), ctx_of("host", key)) as alias:
                    assert alias == "default"

    fresh(probe)


def test_the_test_fallback_stands_for_a_missing_context_only_when_the_tests_set_it(monkeypatch):
    def probe():
        return context.current().kind

    monkeypatch.setattr(context, "_test_fallback", context.SHARED_DATABASE)
    assert fresh(probe) == context.SHARED
    monkeypatch.setattr(context, "_test_fallback", None)
    with pytest.raises(HubContextMissing):
        fresh(probe)
