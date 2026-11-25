"""The device's notices (``notices``): every row of a notice's query, told with its texts filled in."""

import datetime as dt
import json
import re
import string
from collections.abc import Iterable, Mapping
from typing import Any

from django.utils import timezone
from live.context import OperationContext
from live.meta import DeviceNotice, LiveAppConfig
from live.operations import get

from base.business import business_zone
from base.home.module_hooks import hook_failed, logger
from base.home.step_conditions import is_configured

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
    """``text``, an ISO day, hour or instant, as Python's: an instant with an offset on the business's clock
    (``business_zone``), one without as it says. Raises ``ValueError`` for any other text."""
    if ISO_DAY.fullmatch(text):
        return dt.date.fromisoformat(text)
    if ISO_HOUR.fullmatch(text):
        return dt.time.fromisoformat(text)
    if ISO_INSTANT.fullmatch(text):
        value = dt.datetime.fromisoformat(text)
        return timezone.localtime(value, business_zone()) if timezone.is_aware(value) else value
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
