"""Which apps a business has the right to use (BASE-G12; PLAN §20.4–§20.5): the SaaS's photo decides, the Hub applies.

- A module with ``premium = False`` always has it (PLAN-SAAS §2.2: «the free ones always have the right»).
- One with ``premium = True`` needs its id in ``modules[]`` of the business's last photo (``Hub.state``, as the SaaS
  pushed it: ``PUT /internal/hubs/{id}/state``), with ``source`` ``plan`` (included in the plan) or ``purchase``
  (bought), or the right on an app that requires it: the Hub owns the ``requires`` graph and closes the rights over
  it (PLAN §20.5). A right whose ``valid_until`` passed is no right (nobody pushes a photo when a cancelled module's
  period ends, so it is read against the clock). A slug the Hub has no module for is ignored and logged (§20.4.5).
- A demo's hub has every app: it has no photo and nothing to bill, and a demo is where the paid apps are tried.

What a business has no right to is **blocked**: its operations answer 402 ``app_entitlement_blocked``
(:func:`operation_database`, ``LIVE["operation_database"]``), the relay and the Home leave it out
(``base.relay.active_apps``), ``base.session.me`` gives it ``off`` and no menu, and Apps says it needs a subscription,
bought on erplora.com. The Hub never asks the SaaS on a request: it reads the photo it keeps. Without any paid module
in the deployment (today), nothing is read at all.
"""

import datetime as dt
import logging
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import Scope
from live.errors import AppInactive, OperationError
from live.meta import module_configs

from base import registry
from base.tenancy import context as tenancy

logger = logging.getLogger(__name__)

#: Where a module's right comes from: free (not premium), the plan, a purchase, the right on an app that requires it,
#: or nowhere (blocked).
FREE = "free"
PLAN = "plan"
PURCHASE = "purchase"
REQUIRED = "required"
MISSING = "missing"
SOURCES = (FREE, PLAN, PURCHASE, REQUIRED, MISSING)


class EntitlementBlocked(OperationError):
    """An operation of an app the business has no right to (402, PLAN-HUB §1b)."""

    status = 402
    code = "app_entitlement_blocked"


def entitlements(photo: Any, *, now: dt.datetime, configs: Iterable[Any] | None = None) -> dict[str, str]:
    """Every module's source of its right (one of :data:`SOURCES`), by label, for the photo ``photo`` at ``now``."""
    configs = list(module_configs() if configs is None else configs)
    by_label = {config.label: config for config in configs}
    granted = _granted(photo, now, by_label)
    required = _requires_closure(granted, by_label) - set(granted)
    sources = {}
    for config in configs:
        if not _premium(config):
            sources[config.label] = FREE
        elif config.label in granted:
            sources[config.label] = granted[config.label]
        elif config.label in required:
            sources[config.label] = REQUIRED
        else:
            sources[config.label] = MISSING
    return sources


def blocked(photo: Any, *, now: dt.datetime, configs: Iterable[Any] | None = None) -> frozenset[str]:
    """The modules the photo ``photo`` gives no right to at ``now``."""
    return frozenset(label for label, source in entitlements(photo, now=now, configs=configs).items() if source == MISSING)


def blocked_apps(scope: Scope) -> frozenset[str]:
    """The modules blocked on ``scope``'s business now: none on a scope that is no business's, nor on a demo's.

    Reads the registry's row of its host only when some module is paid: without one, nothing is ever blocked."""
    configs = module_configs()
    if scope.kind != tenancy.HUB_SCOPE_KIND or not any(_premium(config) for config in configs):
        return frozenset()
    hub = registry.hub_by_slug(scope.key)
    if hub is not None and hub.is_demo:
        return frozenset()
    return blocked(hub.state if hub is not None else None, now=timezone.now(), configs=configs)


@contextmanager
def operation_database(op, ctx) -> Iterator[str]:
    """``LIVE["operation_database"]``: an operation of an app blocked on its business answers 402 before it opens a
    transaction, and one of an app the business turned off (``base.activation``) 404 ``app_inactive``, read in the
    database of the tenancy (``base.tenancy.context.operation_database``); any other goes on to that database, where a
    manager's pass for it is spent in its transaction (``base.approval_spend``, APP-BASE-5)."""
    if op.app_label in blocked_apps(ctx.scope):
        raise refused(op.app_label, ctx.language)
    from base import activation
    from base.approval_spend import spending

    with tenancy.operation_database(op, ctx) as alias:
        if op.app_label in _module_labels() and op.app_label in activation.off_apps(ctx.scope):
            raise AppInactive(_turned_off(op.app_label, ctx.language))
        with spending(op, ctx, alias) as spent_on:
            yield spent_on


def refused(label: str, language: str) -> EntitlementBlocked:
    """The 402 of ``label``, a paid module this business has no right to, said in ``language``."""
    return EntitlementBlocked(_refusal(label, language))


def _module_labels() -> frozenset[str]:
    return frozenset(config.label for config in module_configs())


def _turned_off(label: str, language: str) -> str:
    names = {config.label: config.verbose_name for config in module_configs()}
    with translation.override(language):
        return gettext("%(app)s is turned off in this business.") % {"app": str(names.get(label, label))}


def requires_of(label: str, configs: Iterable[Any] | None = None) -> frozenset[str]:
    """What module ``label`` needs, transitively: what comes along with it (BASE-G73)."""
    by_label = {config.label: config for config in (module_configs() if configs is None else configs)}
    return frozenset(_requires_closure([label], by_label) - {label})


def _refusal(label: str, language: str) -> str:
    names = {config.label: config.verbose_name for config in module_configs()}
    with translation.override(language):
        return gettext(
            "%(app)s needs a subscription this business does not have. It is bought on erplora.com, in the Store."
        ) % {"app": str(names.get(label, label))}


def _granted(photo: Any, now: dt.datetime, by_label: Mapping[str, Any]) -> dict[str, str]:
    """The modules the photo names with a right still running, with its source (``plan`` or ``purchase``)."""
    rights = photo.get("modules") if isinstance(photo, Mapping) else None
    if not isinstance(rights, list):
        return {}
    granted: dict[str, str] = {}
    for right in rights:
        if not isinstance(right, Mapping) or not isinstance(right.get("id"), str):
            continue
        label = right["id"]
        if label not in by_label:
            logger.warning("base.entitlement.unknown_module %r: the SaaS gives a right to a module the Hub has not.", label)
            continue
        if not _running(right.get("valid_until"), now, label):
            continue
        granted[label] = PLAN if right.get("source") == PLAN else PURCHASE
    return granted


def _running(valid_until: Any, now: dt.datetime, label: str) -> bool:
    if valid_until is None:
        return True
    try:
        ends = dt.datetime.fromisoformat(valid_until)
    except (TypeError, ValueError):
        logger.warning("base.entitlement.unreadable_end %r of %r: the right is not applied.", valid_until, label)
        return False
    if timezone.is_naive(ends):
        ends = timezone.make_aware(ends, dt.UTC)
    return ends > now


def _requires_closure(labels: Iterable[str], by_label: Mapping[str, Any]) -> set[str]:
    """``labels`` and every module they require, transitively (the graph is acyclic: ``live.checks``)."""
    closure: set[str] = set()
    pending = list(labels)
    while pending:
        label = pending.pop()
        if label in closure or label not in by_label:
            continue
        closure.add(label)
        pending.extend(getattr(by_label[label], "requires", ()))
    return closure


def _premium(config: Any) -> bool:
    """A module's ``premium`` (``LiveAppConfig``'s, ``False`` by default; a stand-in may not declare it)."""
    return bool(getattr(config, "premium", False))
