"""The Home's rules (PLAN-HUB round 2026-10-21): what base does with the modules' steps, panels and counters.

Every module declares in its ``LiveAppConfig`` its steps of «Finish setting up your business» (``setup``), its
panels of the dashboard (``widgets``) and its counters of the bell (``bell``), each naming a query of its own
``queries.py``. Base aggregates them in three live queries of ``base/queries.py`` (``base.setup.status``,
``base.widget.list``, ``base.bell.counters``) with the old hub's rules (``crates/runtime/src/setup_status.rs``):

- only the modules on in the scope bring anything, and a module kept out of the store (``listed = False``, the
  reference app ``demo``) only where it shows at all (:func:`shown_modules`);
- a step reads the FIRST row of its query, run by name as the person of the request: done when every condition
  of ``configured_when`` passes on it, pending without a row; a step whose query fails is left out and logged
  (a false «you are missing X» sends the person to fix what may be fine);
- the level is base's, never the module's: ⛔ legal for the list base fixes (``LEGAL_STEPS``) and, where the step's
  row says the hub files in production, for the ones of ``LEGAL_IN_PRODUCTION``; else ``required`` gives functional
  and its absence recommended;
- whoever lacks a step's permission is not told about it, except a pending ⛔ (``actionable: false``): it is what
  will stop their invoice, whoever clears it (hub#435).

A counter whose figure moves as time passes, with no event (a job waiting a minute with no device alive to print
it), names in ``bell_refresh_every`` of its module's ``LiveAppConfig`` (counter key → seconds) how often the bell reads
it again besides its ``refresh_on`` (FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE): the bell is told the shortest
period among the counters the person may see (:func:`bell_refresh_every`), and ``base.E007`` checks the declarations
at start (:func:`bell_refresh_errors`).

The device's notices (PLAN-HUB round 2026-10-23, ``notices``; ``base.notice.list``) run the same way: every row of
a notice's query that passes its ``when`` is told, with the texts filled in from the row in the person's language
(:func:`device_notices`); the shell tells each one once on the device, with the installed app's system notice.

No ORM here: ``queries.py`` reads what the platform's own steps and counters need.
"""

import datetime as dt
import json
import logging
import re
import string
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from django.conf import settings
from django.core import checks
from django.utils import timezone
from django.utils.functional import Promise
from live.context import OperationContext, system_context
from live.errors import PermissionDenied
from live.live_registry import live_registry
from live.meta import DeviceNotice, LiveAppConfig, SetupCheck, all_live_app_configs, module_configs
from live.operations import UnknownOperation, get

logger = logging.getLogger(__name__)

STATE_DONE = "done"
STATE_PENDING = "pending"
#: Ours, not the person's task: nothing could be turned on (the old hub's empty catalogue, hub#371).
STATE_UNAVAILABLE = "unavailable"
LEVEL_LEGAL = "legal"
LEVEL_FUNCTIONAL = "functional"
LEVEL_RECOMMENDED = "recommended"
#: The ⛔ list base fixes: the steps whose absence stops the invoice (the old hub's ``BLOCKING_KEYS``).
LEGAL_STEPS = frozenset({"invoice.business_identity"})
#: The ⛔ steps only where the hub files in production, each with what the first row of its own query says there
#: (PLAN-HUB round 2026-10-21): VeriFactu's way to the AEAT, without which every sale in production is refused; in
#: testing the till sells without it (gh:hub#1726), so there it keeps the level its ``required`` gives.
LEGAL_IN_PRODUCTION = {
    "verifactu.sending_route": (SetupCheck(field="environment", equals="production"),),
}
#: Where a step without ``order`` goes: after every step placed (the old hub's ``DEFAULT_ORDER``).
DEFAULT_ORDER = 500
DEFAULT_STEP_ICON = "ion:settings-outline"
#: The attribute of a module's ``LiveAppConfig`` with how often the bell reads its counters again: key → seconds.
BELL_REFRESH_ATTRIBUTE = "bell_refresh_every"
#: Where an app declares what its plan includes and has spent (:func:`plan_meters`).
PLAN_METER_ATTRIBUTE = "plan_meter"
#: The shortest of those periods: the old hub's bell asked every 30 s, and a shorter one would make every open screen
#: of the business a poller of its hub.
MIN_BELL_REFRESH_SECONDS = 30


def shown_modules(*, demo_hub: bool = False) -> list[LiveAppConfig]:
    """The modules a scope shows anywhere: its menu, «My apps» (``base.session.me``) and the Home's hooks.

    Every module of the store; one kept out of it (the reference app) only where ``SHOW_UNLISTED_MODULES`` says
    (development, the tests and the e2e) or on a demo's hub: never on a customer's.
    """
    return [config for config in module_configs() if config.listed or settings.SHOW_UNLISTED_MODULES or demo_hub]


def home_modules(on: Iterable[str], *, demo_hub: bool = False) -> list[LiveAppConfig]:
    """The modules whose steps, panels and counters reach the Home of a scope where the apps ``on`` are on."""
    on = set(on)
    return [config for config in shown_modules(demo_hub=demo_hub) if config.label in on]


def business_apps() -> list[str]:
    """The modules a business may turn on: every module but those out of the store (the reference app)."""
    return [config.label for config in module_configs() if config.listed]


def first_row(result: Mapping[str, Any]) -> dict | None:
    """The row a step or a counter reads: the first of ``rows``/``items`` in a list, the object itself otherwise."""
    for name in ("rows", "items"):
        rows = result.get(name)
        if isinstance(rows, list):
            return rows[0] if rows else None
    return dict(result)


def truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text != "0" and text.lower() != "false"
    if isinstance(value, list):
        return bool(value)
    return True


def as_text(value: Any) -> str:
    """A value as the old hub compared it with ``equals``: lax, as text (``2`` equals ``"2"``)."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value)


def passes(row: Mapping[str, Any], check: SetupCheck) -> bool:
    value = row.get(check.field)
    if check.truthy is not None:
        return truthy(value) == check.truthy
    if check.equals is not None:
        return as_text(value) == as_text(check.equals)
    return False  # a half-written condition never ticks the step as done


def is_configured(row: Mapping[str, Any] | None, checks: Sequence[SetupCheck]) -> bool:
    return row is not None and all(passes(row, check) for check in checks)


def applies_to_country(countries: Sequence[str], hub_country: str) -> bool:
    if not countries:
        return True
    return bool(hub_country) and any(country.strip().upper() == hub_country.upper() for country in countries)


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


def run_hook(ctx: OperationContext, operation: str, params: Mapping[str, Any]) -> dict | None:
    """The first row of ``operation`` run with ``params`` as the person of ``ctx``.

    Raises whatever the operation raises; the caller leaves the hook out and logs it (``hook_failed``).
    """
    op = get(operation)
    return first_row(op(ctx, op.input.model_validate(dict(params))).model_dump(mode="json"))


def hook_failed(key: str, operation: str, error: BaseException | None = None) -> None:
    """Logs the hook left out with the traceback of ``error`` (outside its ``except``), else of the one handled now."""
    logger.warning("Home: %s left out, its query %s failed.", key, operation, exc_info=error or True)


def plan_meters(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """What the apps of ``configs`` say their plan includes and has spent, for «Usage and plan» of System and the bell
    (BASE-F40), read through each app's own query: base reads no other app's tables. An app declares it on its
    ``LiveAppConfig`` as :data:`PLAN_METER_ATTRIBUTE`: the ``operation``, which of its output's fields are ``used`` and
    ``limit``, its ``label`` and, when its figures may not have come yet, the field that says they did (``measured``).
    Figures not measured yet are ``None``, never a zero; a query that fails is logged and says ``available: False``."""
    meters = []
    for config in configs:
        declared = getattr(config, PLAN_METER_ATTRIBUTE, None)
        if declared is None:
            continue
        meter = {"key": config.label, "label": str(declared["label"]), "used": None, "limit": None, "available": True}
        try:
            row = run_hook(ctx, declared["operation"], {}) or {}
            measured = declared.get("measured")
            if measured is None or row.get(measured) is not None:
                meter.update(used=row[declared["used"]], limit=row[declared["limit"]])
        except Exception:
            hook_failed(f"{config.label}.plan_meter", declared["operation"])
            meter["available"] = False
        meters.append(meter)
    return meters


def module_steps(ctx: OperationContext, configs: Iterable[LiveAppConfig], hub_country: str) -> list[dict]:
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


def translated(value: Any) -> Any:
    """``value`` with its lazy translations, at any depth of its dicts and lists, as text in the language active now.

    A panel's literal props (``options``) may carry them, as the text under a stat's figure; nothing else changes.
    """
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, Mapping):
        return {key: translated(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [translated(item) for item in value]
    return value


def widgets(ctx: OperationContext, configs: Iterable[LiveAppConfig], hub_vertical: str) -> list[dict]:
    """The panels the person of ``ctx`` may put on their dashboard."""
    panels = []
    for config in configs:
        for widget in config.widgets:
            if not ctx.has(widget.permission):
                continue
            if widget.verticals and hub_vertical not in widget.verticals:
                continue
            panels.append(
                {
                    "key": f"{config.label}.{widget.key}",
                    "app": config.label,
                    "title": str(widget.title),
                    "icon": widget.icon,
                    "category": str(widget.category or config.verbose_name),
                    "size": widget.size,
                    "default": widget.default,
                    "kind": widget.kind,
                    "operation": widget.operation,
                    "params": dict(widget.params),
                    "map": dict(widget.map),
                    "options": translated(widget.options),
                    "component": widget.component,
                    "refresh_on": list(widget.refresh_on),
                    "live": widget.operation is not None and live_registry.is_subscribable(widget.operation),
                }
            )
    return panels


def bell_counters(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """The modules' counters of the bell above zero that the person of ``ctx`` may see."""
    counters = []
    for config in configs:
        for counter in config.bell:
            if not ctx.has(counter.permission):
                continue
            key = f"{config.label}.{counter.key}"
            try:
                row = run_hook(ctx, counter.operation, counter.params)
                count = (row or {}).get("count", 0)
                if not isinstance(count, int) or isinstance(count, bool):
                    raise TypeError(f"count is {count!r}, not a whole number")
            except Exception:
                hook_failed(key, counter.operation)
                continue
            if count > 0:
                counters.append(
                    {
                        "key": key,
                        "app": config.label,
                        "count": count,
                        "route": counter.route,
                        "label": str(counter.label),
                        "icon": counter.icon,
                    }
                )
    return counters


def bell_refresh_every(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> int | None:
    """How often the bell of the person of ``ctx`` reads its counters again: the shortest period declared for a counter
    they may see (at zero too: it is the time that raises it), ``None`` when none asks (its events only, as before)."""
    periods = [
        seconds
        for config in configs
        for key, seconds in (getattr(config, BELL_REFRESH_ATTRIBUTE, None) or {}).items()
        for counter in config.bell
        if counter.key == key and ctx.has(counter.permission)
    ]
    return min(periods, default=None)


def bell_refresh_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E007``: ``bell_refresh_every`` maps counters of the app's own bell to whole seconds, none under
    :data:`MIN_BELL_REFRESH_SECONDS`."""
    hint = (
        f"Declare {BELL_REFRESH_ATTRIBUTE} = {{\"<counter key>\": <seconds>}} on the module's LiveAppConfig, for counters of "
        f"its own bell that change as time passes, each at least {MIN_BELL_REFRESH_SECONDS} s."
    )
    errors = []
    for config in configs:
        declared = getattr(config, BELL_REFRESH_ATTRIBUTE, None)
        if declared is None:
            continue
        problems = []
        if not isinstance(declared, Mapping):
            problems.append(f"is {declared!r}, not a mapping of its counters to seconds")
        else:
            counters = {counter.key for counter in getattr(config, "bell", [])}
            for key, seconds in declared.items():
                if key not in counters:
                    problems.append(f"names {key!r}, which is no counter of its bell")
                elif not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < MIN_BELL_REFRESH_SECONDS:
                    problems.append(f"reads {key!r} again every {seconds!r}, not whole seconds from {MIN_BELL_REFRESH_SECONDS}")
        errors += [
            checks.Error(f"{config.label}'s {BELL_REFRESH_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E007")
            for problem in problems
        ]
    return errors


@checks.register("base")
def check_bell_refresh(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """The bell's clock of every app of ours (whatever ``app_configs`` ``manage.py check`` passes)."""
    return bell_refresh_errors(all_live_app_configs())


# --- The device's notices (PLAN-HUB round 2026-10-23) ------------------------------------------------------------

#: What joins the parts of a notice's body (the old shell's «service · day at hour · professional»).
BODY_JOINER = " · "


def rows_of(ctx: OperationContext, operation: str, params: Mapping[str, Any]) -> list[dict]:
    """Every row of ``operation`` run with ``params`` as the person of ``ctx`` (its ``rows`` or ``items``)."""
    op = get(operation)
    result = op(ctx, op.input.model_validate(dict(params))).model_dump(mode="json")
    for name in ("rows", "items"):
        rows = result.get(name)
        if isinstance(rows, list):
            return rows
    return []


def filled(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


#: The ISO forms JSON gives a day, an hour and an instant (``2026-10-23``, ``09:30:00``, ``2026-10-23T08:00:00Z``):
#: only these are read as dates; any other text a template formats as one (``"2026"``) stays the module's mistake.
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
ISO_HOUR = re.compile(r"\d{2}:\d{2}(:\d{2}(\.\d+)?)?")
ISO_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?")


def moment(text: str) -> dt.date | dt.time | dt.datetime:
    """``text``, an ISO day, hour or instant, as Python's: an instant with an offset on the business's clock (Django's
    current zone: ``TIME_ZONE`` in phase 1, the apps' ``business_zone``), one without as it says. Raises
    ``ValueError`` for any other text."""
    if ISO_DAY.fullmatch(text):
        return dt.date.fromisoformat(text)
    if ISO_HOUR.fullmatch(text):
        return dt.time.fromisoformat(text)
    if ISO_INSTANT.fullmatch(text):
        value = dt.datetime.fromisoformat(text)
        return timezone.localtime(value) if timezone.is_aware(value) else value
    raise ValueError(f"{text!r} is not an ISO day, hour or instant")


class RowFormatter(string.Formatter):
    """``str.format`` on a row as JSON gives it (:func:`rows_of`), where a date is text: a field formatted as a date
    (a ``%`` in its spec, ``{at:%H:%M}``) is read as the :func:`moment` it says, each time it is formatted, so
    ``{at:.10}`` beside it still slices the text."""

    def format_field(self, value: Any, format_spec: str) -> str:
        if isinstance(value, str) and "%" in format_spec:
            value = moment(value)
        return super().format_field(value, format_spec)


ROW_FORMATTER = RowFormatter()


def fill(template: Any, row: Mapping[str, Any], key: str) -> str | None:
    """``template`` with the row's fields (its dates formatted by :class:`RowFormatter`), or ``None`` when a field it
    names is empty; one that does not fit the row (a translation that misnames a field, a date format on a text that
    is no ISO date) is logged and is ``None`` too."""
    text = str(template)
    try:
        names = [name for _literal, name, _spec, _conversion in string.Formatter().parse(text) if name is not None]
        if not all(filled(row.get(name)) for name in names):
            return None
        return ROW_FORMATTER.vformat(text, (), row)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        logger.warning("Device notice %s: its text %r does not fit its rows.", key, text, exc_info=True)
        return None


def told(key: str, app: str, notice: DeviceNotice, row: Mapping[str, Any]) -> dict | None:
    """The row as the device tells it, or ``None`` when no title of the notice fills in (logged)."""
    title = next((text for text in (fill(template, row, key) for template in notice.title) if text), None)
    if title is None:
        logger.warning("Device notice %s: no title fills in for row %r; left out.", key, row.get("id"))
        return None
    parts = [fill(template, row, key) for template in notice.body]
    return {
        "key": key,
        "app": app,
        "id": str(row["id"]),
        "at": str(row["at"]),
        "title": title,
        "body": BODY_JOINER.join(part for part in parts if part),
        "route": fill(notice.route, row, key) or "",
    }


def instant(notice: Mapping[str, Any]) -> dt.datetime:
    moment = dt.datetime.fromisoformat(notice["at"])
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


def notice_sources(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[str]:
    """``<app>.<notice>`` of every notice the person of ``ctx`` hears, whether it has rows or not."""
    return [
        f"{config.label}.{notice.key}" for config in configs for notice in config.notices if ctx.has(notice.permission)
    ]


def device_notices(ctx: OperationContext, configs: Iterable[LiveAppConfig]) -> list[dict]:
    """The rows the modules' notices tell that the person of ``ctx`` may see, the newest first.

    A notice whose query fails, or whose rows say no ``id`` or no ``at``, is left out and logged; the notices that
    share a query (and its params) run it once.
    """
    notices = []
    for config in configs:
        results: dict[str, list[dict]] = {}
        for notice in config.notices:
            if not ctx.has(notice.permission):
                continue
            key = f"{config.label}.{notice.key}"
            try:
                asked = json.dumps([notice.operation, dict(notice.params)], sort_keys=True, default=str)
                if asked not in results:
                    results[asked] = rows_of(ctx, notice.operation, notice.params)
                rows = [row for row in results[asked] if is_configured(row, notice.when)]
                notices += [item for item in (told(key, config.label, notice, row) for row in rows) if item]
            except Exception:
                hook_failed(key, notice.operation)
    return sorted(notices, key=instant, reverse=True)


def plan_meter_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E013``: ``plan_meter`` names an operation that exists and fields of its output, with its ``label``."""
    hint = (
        f'Declare {PLAN_METER_ATTRIBUTE} = {{"operation": "<app>.<entity>.<action>", "used": "<field>", "limit": "<field>", '
        '"label": _("…")} on the LiveAppConfig of the module; "measured": "<field>" when its figures may not have come yet.'
    )
    errors = []
    for config in configs:
        declared = getattr(config, PLAN_METER_ATTRIBUTE, None)
        if declared is None:
            continue
        problems = []
        if not isinstance(declared, Mapping):
            problems.append(f"is {declared!r}, not a mapping")
        else:
            if not declared.get("label"):
                problems.append("has no label")
            try:
                fields = get(declared.get("operation")).output.model_fields
            except UnknownOperation:
                problems.append(f"names {declared.get('operation')!r}, which is no operation")
            else:
                names = [declared.get("used"), declared.get("limit")]
                if "measured" in declared:
                    names.append(declared["measured"])
                problems += [f"names {name!r}, which is no field of its output" for name in names if name not in fields]
        errors += [
            checks.Error(f"{config.label}'s {PLAN_METER_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E013")
            for problem in problems
        ]
    return errors


@checks.register("base")
def check_plan_meters(app_configs: Any, **kwargs: Any) -> list[checks.CheckMessage]:
    return plan_meter_errors(all_live_app_configs())
