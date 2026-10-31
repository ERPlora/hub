"""The plan's limits on a hub's database, in each process (PLAN-DB §5 «Límite por plan»; plan 2026-10-22-fase-2-tenencia
§3 S4 and §2, guardrail 12).

A hub with a database of its own gets, in each process, as many transactions at once on its alias as its plan says,
and each of them carries its plan's ``statement_timeout``: Free 1 and 5 s, Starter 3 and 15 s, Standard 6 and 15 s
(each plan above doubles). Both come from the SaaS's photo kept on the hub's row, ``Hub.state["plan"]``
(``max_db_connections``, ``statement_timeout_seconds``); a photo without a usable plan, or no photo yet, gets Free's,
logged once per photo. A newer photo (a greater ``state_version``) resizes the process's limiter at once, without a
restart; an older or equal one changes nothing. PgBouncer's ``max_db_connections`` stays the hard ceiling per database.

Who applies them: the hubs' database engine (:data:`ENGINE`, ``base.tenancy.backend``), which every hub's alias runs on
(``base.tenancy.connections``). Its connection takes a place of its alias's :class:`Limiter` at the first statement of
each transaction (Django's ``atomic`` of an operation, of ``live.operations.atomic``, of the admin, of the worker, or a
statement alone, which is a transaction of its own) and gives it back at its ``COMMIT``, ``ROLLBACK`` or when the
connection closes; its first statement runs after ``SET LOCAL statement_timeout``. No statement on a hub's alias runs
without a place: one that finds none waits :data:`SLOT_WAIT_SECONDS` and answers 503 ``base.hub_busy``
(:class:`HubBusy`), logged with the hub's alias, so the limits can be adjusted by measuring. Control's database and a
hub of phase 1's shared database (``db_name=""``, ``default``) are not limited; the migrator's direct alias (``__ddl``)
neither: its passes have their own budget (``base.tenancy.migrator``).
"""

import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext
from live.errors import OperationError
from psycopg import sql

logger = logging.getLogger(__name__)

#: The engine of every hub's alias (``base.tenancy.connections``): Django's PostgreSQL with these limits.
ENGINE = "base.tenancy.backend"
#: How long a transaction waits for a place of its hub before answering 503.
SLOT_WAIT_SECONDS = 2
#: What a client is told to wait before trying again (``Retry-After`` of the pages that answer 503).
RETRY_AFTER_SECONDS = 1


@dataclass(frozen=True)
class PlanLimits:
    """A plan's limits on its hub's database in one process."""

    max_transactions: int
    statement_timeout_seconds: int


#: The Free plan's, and what a hub whose photo names no usable plan gets.
FREE = PlanLimits(max_transactions=1, statement_timeout_seconds=5)


class HubBusy(OperationError):
    """Every place of the hub in this process is taken, and none was freed within the bounded wait (503)."""

    status = 503
    code = "base.hub_busy"


def _positive(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def plan_limits(state: Any) -> PlanLimits | None:
    """The limits the photo ``state`` (``Hub.state``) gives its hub, or ``None`` when it names no usable plan."""
    plan = state.get("plan") if isinstance(state, Mapping) else None
    if not isinstance(plan, Mapping):
        return None
    transactions = _positive(plan.get("max_db_connections"))
    timeout = _positive(plan.get("statement_timeout_seconds"))
    if transactions is None or timeout is None:
        return None
    return PlanLimits(max_transactions=transactions, statement_timeout_seconds=timeout)


class Slot:
    """One place of a :class:`Limiter`, held by one transaction; it keeps the limits it was taken with."""

    def __init__(self, limiter: Limiter, limits: PlanLimits) -> None:
        self._limiter = limiter
        self.limits = limits
        self._released = False

    def release(self) -> None:
        """Give the place back; a second call does nothing."""
        if not self._released:
            self._released = True
            self._limiter._give_back()


class Limiter:
    """The places of one hub's alias in this process: a semaphore whose size follows the hub's photo."""

    def __init__(self, limits: PlanLimits, *, version: int, alias: str) -> None:
        self._condition = threading.Condition()
        self._limits = limits
        self._version = version
        self._in_use = 0
        self.alias = alias

    @property
    def limits(self) -> PlanLimits:
        return self._limits

    @property
    def version(self) -> int:
        return self._version

    @property
    def in_use(self) -> int:
        return self._in_use

    def resize(self, limits: PlanLimits, *, version: int) -> bool:
        """Take the limits of the photo ``version`` if it is newer than the one in force; whether it was. Growing lets
        the waiting in at once; shrinking lets nobody new in until the places in use are within the new size."""
        with self._condition:
            if version <= self._version:
                return False
            self._limits = limits
            self._version = version
            self._condition.notify_all()
            return True

    def take(self, *, wait: float) -> Slot:
        """A place, waiting at most ``wait`` seconds for one; :class:`HubBusy` (logged) when none came."""
        started = time.monotonic()
        with self._condition:
            if not self._condition.wait_for(lambda: self._in_use < self._limits.max_transactions, timeout=wait):
                logger.warning(
                    "base.hub_busy alias=%s: %s transaction(s) at once already (plan: %s), none ended in %.1f s.",
                    self.alias,
                    self._in_use,
                    self._limits.max_transactions,
                    time.monotonic() - started,
                )
                raise HubBusy(gettext("Too many requests. Try again in a moment."))
            self._in_use += 1
            return Slot(self, self._limits)

    def _give_back(self) -> None:
        with self._condition:
            self._in_use -= 1
            self._condition.notify()


_limiters: dict[str, Limiter] = {}
_lock = threading.Lock()


def _free_for(alias: str, version: int, why: str) -> PlanLimits:
    logger.warning(
        "base.hub_limits_free alias=%s state_version=%s: %s; Free's limits apply (%s transaction(s) at once, %s s).",
        alias,
        version,
        why,
        FREE.max_transactions,
        FREE.statement_timeout_seconds,
    )
    return FREE


def configure(alias: str, hub: Any) -> Limiter:
    """The limiter of ``hub``'s alias in this process, made or resized from its photo (``Hub.state``,
    ``Hub.state_version``) when that photo is newer than the one it follows: what registering the alias does
    (``base.tenancy.connections.register_hub_alias``), at every ``use_hub``."""
    version = getattr(hub, "state_version", 0) or 0
    with _lock:
        limiter = _limiters.get(alias)
        if limiter is not None and version <= limiter.version:
            return limiter
        limits = plan_limits(getattr(hub, "state", None)) or _free_for(alias, version, "its photo names no usable plan")
        if limiter is None:
            limiter = _limiters[alias] = Limiter(limits, version=version, alias=alias)
        else:
            limiter.resize(limits, version=version)
        return limiter


def limiter_for(alias: str) -> Limiter:
    """The limiter of ``alias`` in this process; Free's (logged) for an alias no hub configured."""
    with _lock:
        limiter = _limiters.get(alias)
        if limiter is None:
            limiter = _limiters[alias] = Limiter(
                _free_for(alias, -1, "no hub configured it"), version=-1, alias=alias
            )
        return limiter


def take(alias: str) -> Slot:
    """A place of ``alias``'s hub for one transaction, after a wait of at most :data:`SLOT_WAIT_SECONDS`."""
    return limiter_for(alias).take(wait=SLOT_WAIT_SECONDS)


def statement_timeout_sql(limits: PlanLimits) -> sql.Composed:
    """``SET LOCAL statement_timeout`` of ``limits``: it ends with its transaction (PgBouncer in transaction mode)."""
    return sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(f"{limits.statement_timeout_seconds}s"))
