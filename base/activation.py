"""Turning a business's modules on and off, and the plan's limit on them (PLAN-HUB §9, PLAN-DB §7; BASE-F18, F23–F25).

The rules, without the database: ``base.services`` (``base.app.enable``, ``base.app.disable``) and ``base.queries``
(``base.app.list``, ``base.session.me``) read and write the rows, ``base.models.AppActivation``.

- A module (``kind = "app"``) is ``on`` or ``off`` in a hub. In a hub with its own database its tables are made the
  first time it is turned on (S3; PLAN-DB §7): meanwhile it is ``creating`` and, if making them failed, ``failed`` (tried
  again). Both are **wanted** on: the closure by ``requires``, the plan's limit and what goes off count them as on; only
  ``on`` is active (its operations, the relay, the menu). It is **chosen** when the business turned it on itself; what
  the closure by ``requires`` brought along with it is not, and goes off again with the last chosen module on that
  needs it (Odoo's «an app with its dependencies»).
- **The baseline** (round 2026-10-27): a hub is born with every module off, a demo too. The business turns on what it
  uses, one by one in Apps or all of a blueprint's at once (``base.blueprint.import`` turns them on, then loads); a
  module without its row is off (PLAN-DB: «``off`` o sin fila»). The first change writes every module down
  (``base.services``), so two changes at once have rows to lock. A vertical's template turns on its modules with
  their roots chosen (:func:`template`; 13 of 21 for the restaurant): the modules on that no other module on needs.
- **Every module on** (:func:`every_on`): what a hub had without rows before that round, every module on and its roots
  chosen (today 17 of 27). The migration ``base.0017`` writes it down for every hub of before, so none loses an app,
  and the developer's local hubs ``a`` and ``b`` are seeded with it. The platform always has it, rows or not: a scope
  that is no business's, ERPlora's own hub (``PLATFORM_HUB_SLUG``, Invoicing and VeriFactu always active) and the
  worker's scope (``WORKER_SCOPE_SLUG``), where phase 1 runs every app's scheduled tasks over the tables every hub
  shares (:func:`is_platform`).
- **The plan's limit**: the SaaS's photo carries ``plan.max_apps`` (0, or no key: no limit), how many modules the
  business may *choose*; the ones brought along do not count. A photo with a lower limit than the chosen ones (a plan
  lowered) turns nothing off: it only refuses turning on one more (PLAN §32, point 3).
- **An app's veto**: a module may refuse to go off while it has something unfinished (VeriFactu with records the AEAT
  has not accepted yet, VERIFACTU-F32) by defining ``can_disable(self, ctx) -> str | None`` on its ``LiveAppConfig``:
  the reason, in the person's language, or ``None``. It runs in the transaction of ``base.app.disable``, in the
  language of who asks (``ctx.language``), so a hook that only calls ``gettext`` already answers in it.

What is off is also out of everything that asks which apps are on (``base.relay.active_apps``): its operations answer
404 ``app_inactive`` (``base.entitlement.operation_database``), the relay and the Home leave it out and the menu does
not list it. Its tables are never dropped: turned on again, it has its data.
"""

import logging
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import translation
from live.context import Scope
from live.meta import module_configs

from base.tenancy.context import HUB_SCOPE_KIND

logger = logging.getLogger(__name__)

ON = "on"
OFF = "off"
#: Its tables being made in the hub's own database (the worker's ``ensure_schema``), and making them failed.
CREATING = "creating"
FAILED = "failed"
STATES = (ON, OFF, CREATING, FAILED)
#: What the business wants on: on, or on its way (its tables being made, or tried again after failing).
WANTED = frozenset({ON, CREATING, FAILED})

#: The modules off in a business, kept in Django's cache (Valkey in production, only as a cache) per host: the gate
#: of every operation of a module, the relay and the menu ask it, and the rows are read once per business. A change
#: forgets it at its COMMIT (:func:`forget`), so every process sees it at once; the timeout is only a safety net.
OFF_APPS_CACHE = "base.apps_off:"
OFF_APPS_TTL = 60
#: Beside them, the modules whose tables the hub's own database is getting (``creating``): what the session tells
#: «activating». Kept and forgotten with the apps off; read only when both are kept.
CREATING_APPS_CACHE = "base.apps_creating:"

#: The hosts whose rows the running change wrote and has not committed yet: what it reads of them is never kept.
_changing: ContextVar[frozenset[str]] = ContextVar("base_activation_changing", default=frozenset())

#: ``{label: what it requires}``, a module's direct ``requires`` (acyclic: ``live.checks``).
Graph = Mapping[str, Iterable[str]]


@dataclass(frozen=True)
class Activation:
    """A module's state in one hub, and whether the business chose it."""

    state: str
    chosen: bool

    @property
    def on(self) -> bool:
        """Active: its tables are made and the business has it on."""
        return self.state == ON

    @property
    def wanted(self) -> bool:
        """The business wants it on: on, or its tables still being made (``creating``, ``failed``)."""
        return self.state in WANTED


OFF_ROW = Activation(OFF, False)


def module_graph(configs: Iterable[Any] | None = None) -> dict[str, tuple[str, ...]]:
    """Every module of the deployment with what it requires, in the order of ``INSTALLED_APPS``."""
    return {
        config.label: tuple(getattr(config, "requires", ()) or ())
        for config in (module_configs() if configs is None else configs)
    }


def needs(labels: Iterable[str], graph: Graph) -> set[str]:
    """What ``labels`` require, transitively, without ``labels`` themselves (unless one needs another)."""
    found: set[str] = set()
    pending = [required for label in labels for required in graph[label]]
    while pending:
        label = pending.pop()
        if label not in found:
            found.add(label)
            pending.extend(graph[label])
    return found


def roots(on: Iterable[str], graph: Graph) -> frozenset[str]:
    """The modules of ``on`` that no other module of ``on`` needs, directly or not."""
    on = set(on)
    needed = {label for module in on for label in needs([module], graph) if label != module}
    return frozenset(on - needed)


def template(apps: Iterable[str], graph: Graph) -> dict[str, Activation]:
    """A hub that turns on ``apps`` (closed by ``requires``) and nothing else: ``apps`` on, their roots chosen."""
    on = set(apps)
    chosen = roots(on, graph)
    return {label: Activation(ON, label in chosen) if label in on else OFF_ROW for label in graph}


def baseline(graph: Graph) -> dict[str, Activation]:
    """What a hub that never turned anything on or off has: every module off, none chosen (round 2026-10-27)."""
    return template((), graph)


def every_on(graph: Graph) -> dict[str, Activation]:
    """Every module on, its roots chosen: the hubs of before round 2026-10-27, the local hubs and the platform."""
    return template(graph, graph)


def effective(rows: Mapping[str, Activation], graph: Graph) -> dict[str, Activation]:
    """Every module's state in a hub with ``rows``: the baseline without any; else its row, and off without one."""
    if not rows:
        return baseline(graph)
    return {label: rows.get(label, OFF_ROW) for label in graph}


def required_by(label: str, current: Mapping[str, Activation], graph: Graph) -> list[str]:
    """The modules wanted on that need ``label``, directly or through another one, sorted."""
    return sorted(
        other for other, row in current.items() if other != label and row.wanted and label in needs([other], graph)
    )


def enabling(label: str, current: Mapping[str, Activation], graph: Graph) -> dict[str, Activation]:
    """What turning ``label`` on changes: it, chosen, and what it needs that is off, on and not chosen; one that failed
    is turned on again, keeping whether it was chosen. ``{}`` when it is on, or being created, and chosen already.
    ``KeyError`` for a label that is no module. ``on`` here is what the business asks: a hub with its own database
    makes the tables of one not created yet first (``creating``, ``base.services``)."""
    graph[label]  # noqa: B018 - an unknown module is a programming error
    changes: dict[str, Activation] = {}
    if not (current[label].state in (ON, CREATING) and current[label].chosen):
        changes[label] = Activation(ON, True)
    for required in sorted(needs([label], graph) - {label}):
        row = current[required]
        if row.state in (OFF, FAILED):
            changes[required] = Activation(ON, row.chosen and row.state == FAILED)
    return changes


def disabling(label: str, current: Mapping[str, Activation], graph: Graph) -> dict[str, Activation]:
    """What turning ``label`` off changes: it, and what came along with it (on, not chosen) that no module left on
    needs any more; ``{}`` when it is off. ``ValueError`` when a module on needs it: check :func:`required_by` first.
    A module being created (or that failed) is wanted on: it goes off as one on does, its tables kept."""
    if not current[label].wanted:
        return {}
    needed_by = required_by(label, current, graph)
    if needed_by:
        raise ValueError(f"{label!r} is needed by {', '.join(needed_by)}: they go off first.")
    off = {label}
    brought = needs([label], graph)
    changed = True
    while changed:
        changed = False
        staying = [other for other, row in current.items() if row.wanted and other not in off]
        needed = needs(staying, graph)
        for candidate in sorted(brought - off):
            row = current[candidate]
            if row.wanted and not row.chosen and candidate not in needed:
                off.add(candidate)
                changed = True
    return {other: OFF_ROW for other in [label, *sorted(off - {label})]}


def chosen_on(current: Mapping[str, Activation], *, among: Iterable[str] | None = None) -> int:
    """How many modules wanted on the business chose (``among`` those, if given): what the plan's limit counts, those
    whose tables are being made included."""
    allowed = None if among is None else set(among)
    return sum(
        1 for label, row in current.items() if row.wanted and row.chosen and (allowed is None or label in allowed)
    )


def plan_limit(photo: Any) -> int | None:
    """The photo's ``plan.max_apps``, or ``None``: no limit (0, no key, no plan, or anything that is no count)."""
    plan = photo.get("plan") if isinstance(photo, Mapping) else None
    limit = plan.get("max_apps") if isinstance(plan, Mapping) else None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return None
    return limit


def veto(labels: Iterable[str], *, ctx: Any, configs: Iterable[Any] | None = None) -> tuple[str, str] | None:
    """The first of ``labels`` whose ``can_disable(ctx)`` gives a reason, with it; ``None`` when none refuses. Each
    hook runs in the language of who asks: its reason is said in it, whatever the process runs in."""
    by_label = {config.label: config for config in (module_configs() if configs is None else configs)}
    language = getattr(ctx, "language", None)
    for label in labels:
        hook = getattr(by_label.get(label), "can_disable", None)
        if not callable(hook):
            continue
        with translation.override(language) if language else nullcontext():
            reason = hook(ctx)
        if isinstance(reason, str) and reason.strip():
            return label, reason.strip()
    return None


def is_platform(scope: Scope) -> bool:
    """A scope that is no business choosing its apps: no business's at all, ERPlora's own hub or the worker's (phase
    1 runs every app's scheduled tasks there, over the tables every hub shares). Every module is on in it."""
    return scope.kind != HUB_SCOPE_KIND or scope.key in {settings.PLATFORM_HUB_SLUG, settings.WORKER_SCOPE_SLUG}


def states_of(scope: Scope) -> dict[str, Activation]:
    """Every module's state in ``scope``'s business, read from its rows (``base.queries.app_activations``); the
    platform (:func:`is_platform`) has every module on: nothing of it is ever off."""
    graph = module_graph()
    if is_platform(scope):
        return every_on(graph)
    from base import queries  # base.queries imports this module

    return effective(queries.app_activations(scope.key), graph)


def off_apps(scope: Scope) -> frozenset[str]:
    """The modules off in ``scope``'s business: what ``base.relay.active_apps`` and the operations leave out (those whose
    tables are still being made too: only ``on`` is active).

    From the cache when it has them; else read from the rows and kept, unless the running change wrote them (not
    committed yet). A cache that does not answer is logged and the rows are read: never a guess."""
    if is_platform(scope):
        return frozenset()
    return _kept(scope)[0]


def creating_apps(scope: Scope) -> frozenset[str]:
    """The modules whose tables ``scope``'s business is getting (``creating``), kept with :func:`off_apps`: the session
    tells them «activating». None in the platform, nor in a hub that shares phase 1's database."""
    if is_platform(scope):
        return frozenset()
    return _kept(scope)[1]


def _kept(scope: Scope) -> tuple[frozenset[str], frozenset[str]]:
    """``(off, creating)`` of ``scope``'s business, from the cache when it has both, else from its rows (kept, unless
    the running change wrote them)."""
    keys = (OFF_APPS_CACHE + scope.key, CREATING_APPS_CACHE + scope.key)
    changing = scope.key in _changing.get()
    if not changing:
        kept = _cached_many(keys)
        if kept is not None:
            return frozenset(kept[0]), frozenset(kept[1])
    states = states_of(scope)
    off = frozenset(label for label, row in states.items() if not row.on)
    creating = frozenset(label for label, row in states.items() if row.state == CREATING)
    if not changing:
        try:
            cache.set_many({keys[0]: sorted(off), keys[1]: sorted(creating)}, OFF_APPS_TTL)
        except Exception:
            logger.exception("base.activation.cache_unavailable: the apps off of %s were read and not kept.", scope.key)
    return off, creating


@contextmanager
def changing(host: str) -> Iterator[None]:
    """Around a change of ``host``'s rows (``base.app.enable``/``disable``): what it reads of them is not kept."""
    token = _changing.set(_changing.get() | {host})
    try:
        yield
    finally:
        _changing.reset(token)


def forget(host: str) -> None:
    """Drop ``host``'s apps off from the cache: after the COMMIT of a change, the next read sees it, in every process.
    A cache that does not answer is logged; what it kept ends with its timeout."""
    try:
        cache.delete_many([OFF_APPS_CACHE + host, CREATING_APPS_CACHE + host])
    except Exception:
        logger.exception("base.activation.cache_unavailable: the apps off of %s could not be forgotten.", host)


def _cached_many(keys: tuple[str, str]) -> tuple[list[str], list[str]] | None:
    """Both lists kept under ``keys``, or ``None`` when either is missing or the cache does not answer (logged)."""
    try:
        kept = cache.get_many(list(keys))
    except Exception:
        logger.exception("base.activation.cache_unavailable: the apps off are read from the rows.")
        return None
    found = [kept.get(key) for key in keys]
    if not all(isinstance(value, list) for value in found):
        return None
    return found[0], found[1]
