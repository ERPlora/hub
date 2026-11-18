"""What a counter of the bell says, as ``base.bell.counters`` answers it: the only place that gives a default to the
words a counter leaves out.

A counter (``live.meta.BellCounter``) may declare how grave it is, its heading, one sentence with the consequence and
the label of its button, texts filled in with its ``%(count)d`` and its ``%(label)s``, and the field of its query's row
with its deadline. Read in the language that is on: ``base.bell.counters`` turns on the person's.
"""

import datetime as dt
from collections.abc import Mapping
from typing import Any

from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy, pgettext_lazy
from live.meta import BellCounter

DEFAULT_SEVERITY = "warning"
DEFAULT_ICON = "ion:notifications-outline"
DEFAULT_TITLE = "%(label)s (%(count)d)"
DEFAULT_ACTION = pgettext_lazy("bell button", "Open")

# The platform's own counters: base counts them itself, with no module's query.
FAILED_EVENTS = BellCounter(
    key="failed_events",
    operation="",
    route="/system#events",
    label=_("Failed events"),
    icon="ion:warning-outline",
    severity="danger",
    title=ngettext_lazy("%(count)d failed event", "%(count)d failed events", "count"),
    body=_("An app did not receive what another one sent it: what it had to do stays undone until you send it again."),
    action_label=_("Review the events"),
)
PLAN_LIMITS = BellCounter(
    key="plan_limits",
    operation="",
    route="/system#usage",
    label=_("Plan limits"),
    icon="ion:speedometer-outline",
    severity="warning",
    title=ngettext_lazy("%(count)d plan limit to review", "%(count)d plan limits to review", "count"),
    body=_("Your business is reaching what its plan includes: some things may stop or slow down until you upgrade."),
    action_label=_("See the plan’s usage"),
)


def notice(key: str, counter: BellCounter, row: Mapping[str, Any] | None) -> dict:
    """The bell's row for ``counter`` (``key`` is ``<app>.<counter>``) and the first row of its query, ``row``.

    Raises ``TypeError`` when its count is not a whole number or its deadline not a text, and ``ValueError`` when the
    deadline is not an ISO date-time.
    """
    row = row or {}
    count = row.get("count", 0)
    if not isinstance(count, int) or isinstance(count, bool):
        raise TypeError(f"count is {count!r}, not a whole number")
    label = str(counter.label)
    values = {"count": count, "label": label}
    return {
        "key": key,
        "app": key.split(".", 1)[0],
        "count": count,
        "route": counter.route,
        "label": label,
        "icon": counter.icon or DEFAULT_ICON,
        "severity": counter.severity or DEFAULT_SEVERITY,
        "title": str((counter.title or DEFAULT_TITLE) % values),
        "body": str(counter.body % values) if counter.body else None,
        "action_label": str((counter.action_label or DEFAULT_ACTION) % values),
        "due": _due(counter, row),
    }


def _due(counter: BellCounter, row: Mapping[str, Any]) -> dt.datetime | None:
    value = row.get(counter.due) if counter.due else None
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"due is {value!r}, not an ISO date-time")
    return dt.datetime.fromisoformat(value)
