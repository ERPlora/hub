"""Which database the code running now works on: ``use_hub``, ``use_control`` (PLAN-DB §4; plan 2026-10-22, step 3).

A ``ContextVar`` holds the active :class:`DatabaseContext`; the ``TenantRouter`` (``base.tenancy.router``) reads it
for every model of a hub and ``@operation`` opens its transaction on its alias (:func:`operation_database`, wired as
``settings.LIVE["operation_database"]``). Nested contexts restore the outer one on the way out; ``sync_to_async``
inherits the context and a thread of its own starts without one (the live executor and the print socket enter the
hub again in theirs).

- :func:`use_hub` — one hub: its models go to its alias. A hub with ``db_name`` has its database (its alias is
  registered on first use and its identity checked once per process, ``base.tenancy.identity``); one with
  ``db_name=""`` still shares control's (``default``): phase 1's hubs until the cut of S5 (plan, decision 1).
- :func:`use_control` — the platform: the registry and the demos (``base.hub.*``, ``base.demo.*``); a hub's model
  here is ``HubContextMissing``, the outbox goes to control.
- :func:`use_again` — the context :func:`current` gave elsewhere, entered again by a thread handed work
  (``base.outbound``: what an operation leaves for after its COMMIT runs off the worker's loop, in its hub).
- :func:`use_shared_database` — **transitional (S1–S4)**: phase 1's one database where every hub with
  ``db_name=""`` keeps its data, for what has no single hub yet (the worker's relay and tasks over all of them, the
  admin with no hub chosen, ``manage.py shell``, the platform hub that has no registry row yet). S5 removes it with
  the ``db_name=""`` branch (``tests/test_guardrails.py`` keeps its callers to a list).

Without any of them, a hub's model or operation fails with :class:`HubContextMissing`: it never falls back to
``default``. ``_test_fallback`` is the one exception, set only by the suite's ``conftest.py`` for the tests written
before the tenancy (threads included): never outside the tests.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.db import DEFAULT_DB_ALIAS

HUB = "hub"
CONTROL = "control"
SHARED = "shared"
#: The scope kind of the platform's operations (``base.registry.REGISTRY_SCOPE``): they run on control.
PLATFORM_SCOPE_KIND = "platform"
#: The scope kind of a hub's operations (``base.operations.HostScopeResolver``): its key is the hub's slug.
HUB_SCOPE_KIND = "host"


class HubContextMissing(RuntimeError):
    """A hub's model or operation ran without ``use_hub``: no hub's database is ever guessed."""


class HubContextMismatch(RuntimeError):
    """An operation for one hub ran inside another hub's context: it never reaches the other hub's database."""


@dataclass(frozen=True)
class DatabaseContext:
    """What runs now: a hub (``hub``, its alias), the platform (``control``) or phase 1's shared database."""

    kind: str
    alias: str
    hub: Any = None


CONTROL_DATABASE = DatabaseContext(kind=CONTROL, alias=DEFAULT_DB_ALIAS)
SHARED_DATABASE = DatabaseContext(kind=SHARED, alias=DEFAULT_DB_ALIAS)

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
    """Work on ``hub``'s database until the block ends."""
    if hub.db_name:
        from base.tenancy import connections

        alias = connections.open_hub_alias(hub)
    else:
        alias = DEFAULT_DB_ALIAS
    with _entered(DatabaseContext(kind=HUB, alias=alias, hub=hub)) as active:
        yield active


def use_control() -> Iterator[DatabaseContext]:
    """Work as the platform until the block ends: control's models and outbox, no hub's."""
    return _entered(CONTROL_DATABASE)


def use_shared_database() -> Iterator[DatabaseContext]:
    """Transitional (S1–S4): phase 1's one database, every hub with ``db_name=""`` at once."""
    return _entered(SHARED_DATABASE)


def use_again(active: DatabaseContext) -> AbstractContextManager[DatabaseContext]:
    """Work again, until the block ends, in a context :func:`current` gave elsewhere: what a thread handed work does
    (``base.outbound``), since it starts without one. A hub's goes through :func:`use_hub` (its alias, open in this
    process); control's and the shared database's are entered as they were."""
    if active.kind == HUB:
        return use_hub(active.hub)
    return _entered(active)


def current() -> DatabaseContext:
    """The active context; ``HubContextMissing`` without one."""
    active = _current.get() or _test_fallback
    if active is None:
        raise HubContextMissing(
            "No database context: wrap this in use_hub(hub), use_control() or, for phase 1's shared database, "
            "use_shared_database() (base.tenancy.context)."
        )
    return active


def current_alias() -> str:
    """The alias of the active context (``default`` for control and the shared database)."""
    return current().alias


def current_hub():
    """The hub of the active context, or ``None`` for control and the shared database."""
    return current().hub


@contextmanager
def operation_database(op, ctx) -> Iterator[str]:
    """Where ``op`` runs for ``ctx``: the alias ``@operation`` opens its transaction on (``LIVE["operation_database"]``).

    A platform operation (the registry, the demos) runs on control, from anywhere. A hub's runs in the hub of the
    active context, and only if it is that hub (``HubContextMismatch`` for another one's); without one, or in
    control's, ``HubContextMissing``. The shared database (S1–S4) runs any hub's on ``default``.
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
