"""The modules' steps of «Finish setting up your business»: their level, their state and the list."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from live.context import OperationContext, system_context
from live.errors import PermissionDenied
from live.meta import LiveAppConfig, SetupCheck

from base.business import country_or_market
from base.home.module_hooks import hook_failed, run_hook
from base.home.step_conditions import is_configured

STATE_DONE = "done"
STATE_PENDING = "pending"
#: Ours, not the person's task: nothing could be turned on (the old hub's empty catalogue).
STATE_UNAVAILABLE = "unavailable"
LEVEL_LEGAL = "legal"
LEVEL_FUNCTIONAL = "functional"
LEVEL_RECOMMENDED = "recommended"
#: The ⛔ list base fixes: the steps whose absence stops the invoice (the old hub's ``BLOCKING_KEYS``).
LEGAL_STEPS = frozenset({"invoice.business_identity"})
#: The ⛔ steps only where the hub files in production, each with what the first row of its own query says there:
#: VeriFactu's way to the AEAT, without which every sale in production is refused; in testing the till sells without
#: it, so there it keeps the level its ``required`` gives.
LEGAL_IN_PRODUCTION = {
    "verifactu.sending_route": (SetupCheck(field="environment", equals="production"),),
}
#: Where a step without ``order`` goes: after every step placed (the old hub's ``DEFAULT_ORDER``).
DEFAULT_ORDER = 500
DEFAULT_STEP_ICON = "ion:settings-outline"


def applies_to_country(countries: Sequence[str], hub_country: str) -> bool:
    """Whether a step for ``countries`` (none: every one) is for a hub of ``hub_country``. A hub without a country (a
    demo, ERPlora's own) is in ERPlora's market, Spain (``base.business.country_or_market``, hub#682): it is told the
    Spanish steps, as VeriFactu counts it, and no other country's."""
    if not countries:
        return True
    country = country_or_market(hub_country)
    return any(declared.strip().upper() == country for declared in countries)


def may_be_legal(key: str) -> bool:
    return key in LEGAL_STEPS or key in LEGAL_IN_PRODUCTION


def level_of(key: str, required: bool, row: Mapping[str, Any] | None = None) -> str:
    """The step's level, on the first row of its query (``row``) for the walls of production."""
    if key in LEGAL_STEPS or (key in LEGAL_IN_PRODUCTION and is_configured(row, LEGAL_IN_PRODUCTION[key])):
        return LEVEL_LEGAL
    return LEVEL_FUNCTIONAL if required else LEVEL_RECOMMENDED


def document(items: list[dict]) -> dict:
    """``{total, pending, unavailable, blocking_pending, items}``, the items by ``order`` then ``key``."""
    ordered = sorted(items, key=lambda item: (item["order"], item["key"]))
    return {
        "total": len(ordered),
        "pending": sum(item["state"] == STATE_PENDING for item in ordered),
        "unavailable": sum(item["state"] == STATE_UNAVAILABLE for item in ordered),
        "blocking_pending": sum(
            item["level"] == LEVEL_LEGAL and item["state"] == STATE_PENDING for item in ordered
        ),
        "items": ordered,
    }


def module_steps(ctx: OperationContext, configs: Iterable[LiveAppConfig], hub_country: str) -> list[dict]:  # noqa: C901
    """The modules' steps of the list, as the person of ``ctx`` may be told about them."""
    items = []
    for config in configs:
        for step in config.setup:
            if not applies_to_country(step.countries, hub_country):
                continue
            key = f"{config.label}.{step.key}"
            wall = may_be_legal(key)
            actionable = ctx.has(step.permission)
            if not actionable and not wall:
                continue
            denied: PermissionDenied | None = None
            try:
                row = run_hook(ctx, step.operation, step.params)
            except PermissionDenied as error:
                if not wall:
                    hook_failed(key, step.operation)
                    continue
                # A wall is a fact about the hub: whoever may not read it still has it in front of the invoice.
                denied = error
                try:
                    row = run_hook(system_context(ctx.scope), step.operation, step.params)
                except Exception:
                    hook_failed(key, step.operation)
                    continue
            except Exception:
                hook_failed(key, step.operation)
                continue
            level = level_of(key, step.required, row)
            if denied is not None and level != LEVEL_LEGAL:
                # No wall here after all (a hub in testing): left out, as any step the person may not read; logged
                # only for whoever may do it (as before), never for whoever is not told about it at all.
                if actionable:
                    hook_failed(key, step.operation, denied)
                continue
            state = STATE_DONE if is_configured(row, step.configured_when) else STATE_PENDING
            if not actionable and (level != LEVEL_LEGAL or state != STATE_PENDING):
                continue
            items.append(
                item(
                    key,
                    config.label,
                    state=state,
                    required=step.required,
                    level=level,
                    actionable=actionable,
                    title=step.title,
                    description=step.description,
                    icon=step.icon or DEFAULT_STEP_ICON,
                    route=step.route,
                    order=DEFAULT_ORDER if step.order is None else step.order,
                )
            )
    return items


def item(key: str, app: str, **fields: Any) -> dict:
    """One item of the list; its texts (usually lazy translations) in the language active now."""
    return {
        "key": key,
        "app": app,
        **fields,
        "title": str(fields["title"]),
        "description": str(fields["description"]),
    }
