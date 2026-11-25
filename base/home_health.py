"""The Home's health row: what each app on says of its own, for who runs the business (BASE-F02).

An app declares ``health`` on its ``LiveAppConfig``: the query of its own whose first row says its state in ``state``
(:data:`APP_STATES`), its ``params``, the ``permission`` it needs, the ``title`` of each state (:data:`STATES`) and where
to fix it (``route``, with the ``action`` that leads there). Base runs the query as the person (:func:`health_items`) and
says ``unknown`` when it cannot tell, never ``ok``: a fault in the reading is nobody's task, so it has no action.
``base.E021`` checks the declarations at start (:func:`health_errors`). What each state means is its app's.
"""

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from django.core import checks
from live.context import OperationContext
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import UnknownOperation, get

from base import home
from base.permissions import ADMINISTER_HUB

logger = logging.getLogger(__name__)

HEALTH_ATTRIBUTE = "health"
REQUIRED_FIELDS = frozenset({"operation", "route", "action", "titles"})
HEALTH_FIELDS = REQUIRED_FIELDS | {"params", "permission"}
OK = "ok"
NO_SIGNAL = "no_signal"
NOT_CONFIGURED = "not_configured"
UNKNOWN = "unknown"
#: What an app's query may answer.
APP_STATES = frozenset({OK, NO_SIGNAL, NOT_CONFIGURED})
#: What the row may say: the app's states and base's own, when it cannot tell.
STATES = APP_STATES | {UNKNOWN}
#: The states the person can fix, with the app's action.
FIXABLE = frozenset({NO_SIGNAL, NOT_CONFIGURED})


def health_items(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """``{key, app, state, title, action, route}`` of each app of ``configs`` that declares its health and the person of
    ``ctx`` may see, in the order of ``configs``; nothing for whoever does not run the business."""
    if not ctx.has(ADMINISTER_HUB):
        return []
    items = []
    for config in configs:
        declared = getattr(config, HEALTH_ATTRIBUTE, None)
        if declared is None or not ctx.has(declared.get("permission")):
            continue
        state = read_state(ctx, config.label, declared)
        fixable = state in FIXABLE
        items.append(
            {
                "key": config.label,
                "app": config.label,
                "state": state,
                "title": str(declared["titles"][state]),
                "action": str(declared["action"]) if fixable else None,
                "route": declared["route"] if fixable else None,
            }
        )
    return items


def read_state(ctx: OperationContext, label: str, declared: Mapping[str, Any]) -> str:
    """The state the app's query answers, or :data:`UNKNOWN` (logged) when it fails or answers one it may not."""
    try:
        row = home.module_hooks.run_hook(ctx, declared["operation"], declared.get("params") or {}) or {}
    except Exception:
        home.module_hooks.hook_failed(f"{label}.health", declared["operation"])
        return UNKNOWN
    state = row.get("state")
    if state not in APP_STATES:
        logger.warning("Home: %s.health left unknown, its query %s answered %r.", label, declared["operation"], state)
        return UNKNOWN
    return state


def operation_problems(name: Any) -> list[str]:
    try:
        fields = get(name).output.model_fields
    except UnknownOperation:
        return [f"names {name!r}, which is no operation"]
    return [] if "state" in fields else [f"names {name!r}, whose output says no state"]


def titles_problems(titles: Any) -> list[str]:
    if not isinstance(titles, Mapping):
        return [f"has titles {titles!r}, not a mapping of each state to its title"]
    problems = [f"has no title for {state!r}" for state in sorted(STATES) if not titles.get(state)]
    return problems + [f"has a title for {state!r}, which is no state" for state in sorted(set(titles) - STATES)]


def health_problems(config: LiveAppConfig, declared: Any) -> list[str]:
    """What is wrong with ``config``'s :data:`HEALTH_ATTRIBUTE`."""
    if not isinstance(declared, Mapping):
        return [f"is {declared!r}, not a mapping"]
    problems = [f"has {field!r}, which it does not take" for field in sorted(set(declared) - HEALTH_FIELDS)]
    problems += [f"has no {field!r}" for field in sorted(REQUIRED_FIELDS - set(declared))]
    problems += operation_problems(declared.get("operation"))
    if not isinstance(declared.get("params", {}), Mapping):
        problems.append(f"has params {declared['params']!r}, not a mapping")
    permission = declared.get("permission")
    if permission is not None and permission not in config.permissions:
        problems.append(f"needs {permission!r}, which is no permission of the app")
    route = declared.get("route")
    if not isinstance(route, str) or not route.startswith("/"):
        problems.append(f"leads to {route!r}, which is no route of the app")
    if "action" in declared and not declared["action"]:
        problems.append("has an empty action")
    return problems + titles_problems(declared.get("titles"))


def health_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E021``: ``health`` names a query of the app whose output says its ``state``, a permission of the app if
    any, the route and action that fix it and a title for each state: a slip would leave the row blank or wrong."""
    hint = (
        f'Declare {HEALTH_ATTRIBUTE} = {{"operation": "<app>.<entity>.<action>", "params": {{…}}, "permission": '
        '"<app>.<action>", "route": "/<app>/…", "action": _("…"), "titles": {"ok": _("…"), "no_signal": _("…"), '
        '"not_configured": _("…"), "unknown": _("…")}} on the LiveAppConfig of the module.'
    )
    errors = []
    for config in configs:
        declared = getattr(config, HEALTH_ATTRIBUTE, None)
        if declared is None:
            continue
        errors += [
            checks.Error(f"{config.label}'s {HEALTH_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E021")
            for problem in health_problems(config, declared)
        ]
    return errors


@checks.register("base")
def check_health(app_configs: Any, **kwargs: Any) -> list[checks.CheckMessage]:
    return health_errors(all_live_app_configs())
