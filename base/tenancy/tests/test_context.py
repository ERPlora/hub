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

pytestmark = pytest.mark.usefixtures("no_test_fallback", "aliases_without_a_server")


@pytest.fixture
def aliases_without_a_server(monkeypatch):
    """A hub's alias as ``base.tenancy.connections`` names it, without registering it nor reading its identity: these
    tests are about the context, not about a server."""
    from base.tenancy import connections

    monkeypatch.setattr(connections, "open_hub_alias", lambda hub: f"hub_{hub.id.hex}")


def own_hub(slug: str):
    """A hub with its database (``db_name``): its alias is its own."""
    hub_id = uuid.uuid7()
    return SimpleNamespace(id=hub_id, slug=slug, db_name=f"test_{hub_id.hex}")


def shared_hub(slug: str):
    """A business of phase 1 not yet cut (``db_name=""``): since S5 it is never entered."""
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


def test_a_hub_runs_on_its_own_alias():
    a = own_hub("a")

    def probe():
        with context.use_hub(a) as active:
            assert active.kind == context.HUB
            assert active.hub is a
            assert context.current_alias() == f"hub_{a.id.hex}"
            assert context.current_hub() is a

    fresh(probe)


def test_a_business_without_its_own_database_is_never_entered_nor_sent_to_control():
    # S5: phase 1's shared database is gone; a business not yet cut is not served (its host answers 503).
    a = shared_hub("a")

    def probe():
        with pytest.raises(context.HubWithoutDatabase, match="a"), context.use_hub(a):
            pass
        with pytest.raises(HubContextMissing):
            context.current()

    fresh(probe)
    assert not context.serves_hubs_without_database()


def test_there_is_no_shared_database_any_more():
    assert not hasattr(context, "use_shared_database")
    assert not hasattr(context, "SHARED_DATABASE")
    assert not hasattr(context, "SHARED")


def test_nested_contexts_restore_the_outer_one_even_after_an_error():
    a, b = own_hub("a"), own_hub("b")

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


async def test_sync_to_async_inherits_the_context():
    a = own_hub("a")
    with context.use_hub(a):
        assert await sync_to_async(context.current_hub)() is a


def test_a_thread_of_its_own_starts_without_one():
    a = own_hub("a")
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


@pytest.mark.parametrize("kind", [context.HUB, context.CONTROL])
def test_a_thread_handed_work_enters_again_the_context_it_was_given_and_leaves_none_behind(kind):
    # base.outbound: the job of an operation runs in another thread, in the database of the hub that asked.
    a = own_hub("a")
    entered = {context.HUB: lambda: context.use_hub(a), context.CONTROL: context.use_control}[kind]
    seen = []

    def in_thread(given):
        with context.use_again(given):
            seen.append((context.current().kind, context.current_hub(), context.current_alias()))
        try:
            context.current()
        except HubContextMissing:
            seen.append("none after it")

    def probe():
        with entered():
            given = context.current()
        thread = threading.Thread(target=in_thread, args=(given,))
        thread.start()
        thread.join()

    fresh(probe)
    alias = f"hub_{a.id.hex}" if kind == context.HUB else "default"
    assert seen == [(kind, a if kind == context.HUB else None, alias), "none after it"]


# ── The database of an operation (live's LIVE["operation_database"]) ──────────────────────────────────────────


def test_a_platform_operation_runs_on_control_from_anywhere():
    a = own_hub("a")

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
    a = own_hub("a")

    def probe():
        with context.use_hub(a), context.operation_database(op(), ctx_of("host", "a")) as alias:
            assert alias == f"hub_{a.id.hex}"
            assert context.current_hub() is a

    fresh(probe)


def test_an_operation_for_another_hub_never_runs_in_this_one():
    a = own_hub("a")

    def probe():
        with context.use_hub(a), pytest.raises(HubContextMismatch, match="b"):
            with context.operation_database(op(), ctx_of("host", "b")):
                pass

    fresh(probe)


def test_the_test_fallback_stands_for_a_missing_context_only_when_the_tests_set_it(monkeypatch):
    from base.tenancy.tests.legacy import LEGACY

    a = shared_hub("a")

    def probe():
        with context.use_hub(a) as entered:
            assert entered.alias == "default" and entered.hub is a
        with context.operation_database(op(), ctx_of("host", "b")) as alias:
            assert alias == "default"
        return context.current().kind

    monkeypatch.setattr(context, "_test_fallback", LEGACY)
    # The suite's tests written before the tenancy: every business of theirs on control's test database.
    assert fresh(probe) == LEGACY.kind
    assert context.serves_hubs_without_database()
    monkeypatch.setattr(context, "_test_fallback", None)
    with pytest.raises(context.HubWithoutDatabase):
        fresh(probe)


def test_the_admin_without_a_business_works_on_control_and_under_the_suites_fallback_on_it(monkeypatch):
    from base.tenancy.tests.legacy import LEGACY

    def probe():
        with context.use_admin_without_a_business() as active:
            return active.kind

    assert fresh(probe) == context.CONTROL
    monkeypatch.setattr(context, "_test_fallback", LEGACY)
    assert fresh(probe) == LEGACY.kind
