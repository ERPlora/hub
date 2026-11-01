"""Which database the code running now works on: ``use_hub``, ``use_control`` (PLAN-DB §4; plan 2026-10-22, step 3).

A ``ContextVar`` holds the active :class:`DatabaseContext`; the ``TenantRouter`` (``base.tenancy.router``) reads it
for every model of a hub and ``@operation`` opens its transaction on its alias (:func:`operation_database`, wired as
``settings.LIVE["operation_database"]``). Nested contexts restore the outer one on the way out; ``sync_to_async``
inherits the context and a thread of its own starts without one (the live executor and the print socket enter the
hub again in theirs).

- :func:`use_hub` — one hub: its models go to its database's alias (registered on first use and its identity checked
  once per process, ``base.tenancy.identity``). A business without a database of its own (``db_name=""``: phase 1's,
  before its cut) is never entered (:class:`HubWithoutDatabase`): since S5 phase 1's shared database is gone, its
  host answers 503 until ``cut_shared_hubs`` gives it one (``base.tenancy.cut``).
- :func:`use_control` — the platform: the registry and the demos (``base.hub.*``, ``base.demo.*``); a hub's model
  here is ``HubContextMissing``, the outbox goes to control.
- :func:`use_again` — the context :func:`current` gave elsewhere, entered again by a thread handed work
  (``base.outbound``: what an operation leaves for after its COMMIT runs off the worker's loop, in its hub).

Without any of them, a hub's model or operation fails with :class:`HubContextMissing`: it never falls back to
``default``. ``_test_fallback`` is the one exception, set only by the suite's ``conftest.py``: the tests written before
the tenancy keep every business of theirs (``db_name=""``) in control's test database
(``base/tenancy/tests/legacy.py``), so under it they run without a context and such a business is entered there
(:func:`serves_hubs_without_database`). Never outside the tests.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.db import DEFAULT_DB_ALIAS

HUB = "hub"
CONTROL = "control"
#: The scope kind of the platform's operations (``base.registry.REGISTRY_SCOPE``): they run on control.
PLATFORM_SCOPE_KIND = "platform"
#: The scope kind of a hub's operations (``base.operations.HostScopeResolver``): its key is the hub's slug.
HUB_SCOPE_KIND = "host"


class HubContextMissing(RuntimeError):
    """A hub's model or operation ran without ``use_hub``: no hub's database is ever guessed."""


class HubContextMismatch(RuntimeError):
    """An operation for one hub ran inside another hub's context: it never reaches the other hub's database."""


class HubWithoutDatabase(RuntimeError):
    """A business without a database of its own (phase 1's, not yet cut): it is never entered nor served (S5)."""


@dataclass(frozen=True)
class DatabaseContext:
    """What runs now: a hub (``hub``, its alias) or the platform (``control``); the suite's fallback has a kind of its
    own (``base/tenancy/tests/legacy.py``)."""

    kind: str
    alias: str
    hub: Any = None


CONTROL_DATABASE = DatabaseContext(kind=CONTROL, alias=DEFAULT_DB_ALIAS)

_current: ContextVar[DatabaseContext | None] = ContextVar("tenancy_database_context", default=None)
#: Set only by the tests' conftest.py: what a test written before the tenancy runs on without a context.
_test_fallback: DatabaseContext | None = None


@contextmanager
def _entered(active: DatabaseContext) -> Iterator[DatabaseContext]:
    token = _current.set(active)
    try:
        yield active
    finally:
        _current.reset(token)


@contextmanager
def use_hub(hub) -> Iterator[DatabaseContext]:
    """Work on ``hub``'s database until the block ends; :class:`HubWithoutDatabase` for a business without one."""
    if hub.db_name:
        from base.tenancy import connections

        alias = connections.open_hub_alias(hub)
    elif _test_fallback is not None:
        # The suite's tests written before the tenancy: their businesses' rows are in control's test database.
        alias = _test_fallback.alias
    else:
        raise HubWithoutDatabase(
            f"The business {hub.slug or hub.id} has no database of its own yet: it is not served until "
            "manage.py cut_shared_hubs gives it one (base.tenancy.cut)."
        )
    with _entered(DatabaseContext(kind=HUB, alias=alias, hub=hub)) as active:
        yield active


def use_control() -> Iterator[DatabaseContext]:
    """Work as the platform until the block ends: control's models and outbox, no hub's."""
    return _entered(CONTROL_DATABASE)


def use_admin_without_a_business() -> AbstractContextManager[DatabaseContext]:
    """Where the admin works with no business chosen (``base.middleware``): control. Under the suite's fallback, the
    fallback itself: control's test database, with the rows of every business of the tests written before the
    tenancy, as the admin showed them in phase 1."""
    return use_control() if _test_fallback is None else _entered(_test_fallback)


def serves_hubs_without_database() -> bool:
    """Whether a business without a database of its own is entered and served: never in production (S5), only under
    the suite's fallback (``_test_fallback``), where the tests written before the tenancy keep their businesses."""
    return _test_fallback is not None


def use_again(active: DatabaseContext) -> AbstractContextManager[DatabaseContext]:
    """Work again, until the block ends, in a context :func:`current` gave elsewhere: what a thread handed work does
    (``base.outbound``), since it starts without one. A hub's goes through :func:`use_hub` (its alias, open in this
    process); control's is entered as it was."""
    if active.kind == HUB:
        return use_hub(active.hub)
    return _entered(active)


def current() -> DatabaseContext:
    """The active context; ``HubContextMissing`` without one."""
    active = _current.get() or _test_fallback
    if active is None:
        raise HubContextMissing(
            "No database context: wrap this in use_hub(hub) or use_control() (base.tenancy.context)."
        )
    return active


def current_for(scope) -> DatabaseContext:
    """The context where work for ``scope``'s business runs when the active context asks for it (``base.outbound``):
    the active one. A hub holds only its own rows, and another hub's operation there is refused
    (``HubContextMismatch``): no work ever reaches another hub's database."""
    return current()


def current_alias() -> str:
    """The alias of the active context (``default`` for control)."""
    return current().alias


def current_hub():
    """The hub of the active context, or ``None`` for control."""
    return current().hub


@contextmanager
def operation_database(op, ctx) -> Iterator[str]:
    """Where ``op`` runs for ``ctx``: the alias ``@operation`` opens its transaction on (``LIVE["operation_database"]``).

    A platform operation (the registry, the demos) runs on control, from anywhere. A hub's runs in the hub of the
    active context, and only if it is that hub (``HubContextMismatch`` for another one's); without one, or in
    control's, ``HubContextMissing``. The suite's fallback runs any hub's on control's test database.
    """
    if ctx.scope.kind == PLATFORM_SCOPE_KIND:
        with use_control() as active:
            yield active.alias
        return
    active = current()
    if active.kind == CONTROL:
        raise HubContextMissing(f"{op.name} is a hub's operation: run it inside use_hub(hub), not on control.")
    if active.kind == HUB and ctx.scope.kind == HUB_SCOPE_KIND and ctx.scope.key != active.hub.slug:
        raise HubContextMismatch(
            f"{op.name} runs for the hub {ctx.scope.key!r} inside the context of {active.hub.slug!r}."
        )
    yield active.alias
