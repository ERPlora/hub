"""The document of an automation: data paths, ``{{…}}`` templates, conditions, schedules and the
permissions its steps ask for (WORKBOOK «Para quien lo mantiene»). Pure: no database, no clock.

- A **path** is ``<root>.<field>[.<field>…]`` with the roots ``input`` (what the event or the manual run
  brought) and ``steps`` (``steps.<id>.<field>``: what an earlier step left). It keeps the type of what
  it points at. There is no index into a list: the old engine could not walk one either.
- A **template** is text with ``{{path}}`` inside; it is always text, and a missing field is empty. Each datum goes
  in as the code keeps it («true», an ISO day, an amount in cents), for a machine; a text a person reads passes a
  ``say`` that writes each one in words (``queries.words_for``, FLOW-F28 and F31).
- A **condition** is ``{path: {operator: value}}``, every comparison at once. A field that is not there
  never matches, except with ``exists: false``.
- A **schedule** is every day, week (``weekday``, Monday 0) or month (``day``) at ``time``, read in the
  business's time zone (``python-dateutil``'s ``rrule``: a day a month lacks is skipped that month).
- A **call** (``http``, FLOW-F27) is the one step whose texts may also read ``secret.<NAME>`` (a kept
  secret) and ``run.idempotency_key``; its address is written by hand up to its host, and its permission
  is its origin (``http:https://host``).
"""

import datetime as dt
import json
import re
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, urlsplit

from dateutil import rrule

ROOTS = ("input", "steps")
OPERATORS = ("eq", "neq", "in", "exists", "contains", "gt", "gte", "lt", "lte")
#: Most steps one automation holds; most automations are one trigger and one action.
MAX_STEPS = 50
#: A wait is a minute at least and 30 days at most (the old engine's ceiling of a parked run).
MIN_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 30 * 24 * 3600
#: Most automations a chain of events may cross before it is stopped (WORKBOOK «Sin cadenas infinitas»).
#: The chain is read from the outbox actor (`flow_run:<id>`) of the event that starts a run, so it only
#: follows the events a step records itself: when a step's event goes through another app's reaction
#: first (which runs as the system), the events of that reaction carry `system` and the chain starts
#: again. Inheriting it needs the outbox relay of phase 2 to run each reaction with the actor of the
#: event it delivers (base/ and the apps' `react`), not this app.
MAX_CHAIN = 8
#: The kinds of step this engine runs.
STEP_KINDS = ("command", "query", "condition", "delay", "http", "ask", "assistant")
#: What a call's texts may read besides the automation's data: a kept secret, and the call's own key.
CALL_ONLY_RE = re.compile(r"^(?:secret\.[A-Z][A-Z0-9_]{0,63}|run\.idempotency_key)$")
#: The prefix of a call's permission: ``http:https://host[:port]``.
HTTP_GRANT = "http:"

_SEGMENT = r"[A-Za-z_][A-Za-z0-9_]*"
PATH_RE = re.compile(rf"^(?:{'|'.join(ROOTS)})(?:\.{_SEGMENT})+$")
TEMPLATE_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
_MISSING = object()
#: How a text says the datum ``value`` its path names: ``say(path, value) -> text``.
Say = Callable[[str, Any], str]


def is_path(text: Any) -> bool:
    """Whether ``text`` is a path (and is read as one, not as a literal)."""
    return isinstance(text, str) and bool(PATH_RE.match(text))


def lookup(path: str, data: dict) -> tuple[bool, Any]:
    """``(found, value)`` of ``path`` in ``data`` (``{"input": …, "steps": …}``)."""
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def resolve(value: Any, data: dict, say: Say | None = None) -> Any:
    """The value of ``value`` for ``data``: a path its value, a template its text, a literal itself. With ``say`` (a
    text a person reads), each datum a template inserts — and a path alone — is the text ``say`` writes for it."""
    if isinstance(value, dict):
        return {key: resolve(item, data, say) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, data, say) for item in value]
    if not isinstance(value, str):
        return value
    if is_path(value):
        found = lookup(value, data)[1]
        return found if say is None or found is None else say(value, found)
    if TEMPLATE_RE.search(value):
        written = say or (lambda _path, datum: _text(datum))
        return TEMPLATE_RE.sub(lambda match: _said(written, match.group(1), data), value)
    return value


def _said(say: Say, path: str, data: dict) -> str:
    """The datum ``path`` names, as ``say`` writes it; a missing one, empty."""
    found = lookup(path, data)[1]
    return "" if found is None else say(path, found)


def references(value: Any) -> list[str]:
    """Every path ``value`` reads, in order (a template's inner text even when it is no path)."""
    found: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            found += references(item)
    elif isinstance(value, list):
        for item in value:
            found += references(item)
    elif isinstance(value, str):
        if is_path(value):
            found.append(value)
        else:
            found += [match.group(1) for match in TEMPLATE_RE.finditer(value)]
    return found


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fill(text: str, data: dict, say: Say | None = None) -> str:
    """``text`` with its ``{{…}}`` data filled in, always text (a path alone is its value as text); with ``say``,
    each datum as it writes it."""
    return _text(resolve(text, data, say))


# --- Conditions -------------------------------------------------------------------------------------


def number(value: Any) -> Decimal | None:
    """``value`` as a number: an int, a float or numeric text; never a boolean."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
    return None


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    left, right = number(actual), number(expected)
    if left is not None and right is not None:
        return left == right
    return actual == expected


def _order(actual: Any, expected: Any, operator: str) -> bool:
    left, right = number(actual), number(expected)
    if left is None or right is None:
        return False
    return {
        "gt": left > right,
        "gte": left >= right,
        "lt": left < right,
        "lte": left <= right,
    }[operator]


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str):
        return str(expected).casefold() in actual.casefold()
    if isinstance(actual, list):
        return any(_equal(item, expected) for item in actual)
    return False


def _compare(found: bool, actual: Any, operator: str, expected: Any) -> bool:
    if operator == "exists":
        present = found and actual is not None
        return present is bool(expected)
    if not found:
        return False
    if operator == "eq":
        return _equal(actual, expected)
    if operator == "neq":
        return not _equal(actual, expected)
    if operator == "in":
        return isinstance(expected, list) and any(
            _equal(actual, item) for item in expected
        )
    if operator == "contains":
        return _contains(actual, expected)
    return _order(actual, expected, operator)


def _compared_with(expected: Any, data: dict) -> tuple[bool, Any]:
    """``(there, value)`` of what a comparison compares with: a literal itself; another datum (a path, a
    template, a list of them) read like any value — a path to a datum that is not there is not there."""
    if is_path(expected):
        return lookup(expected, data)
    return True, resolve(expected, data)


def failed_clauses(condition: dict, data: dict) -> list[dict]:
    """The comparisons of ``condition`` that do not hold for ``data``, as ``{path, op, value}`` (the value
    as written: a path stays a path, for the words that name it)."""
    failed = []
    for path, comparisons in condition.items():
        found, actual = lookup(path, data)
        for operator, expected in comparisons.items():
            there, value = _compared_with(expected, data)
            if not (there and _compare(found, actual, operator, value)):
                failed.append({"path": path, "op": operator, "value": expected})
    return failed


def readable(condition: Any) -> bool:
    """Whether ``condition`` is one the engine can evaluate: paths to non-empty known comparisons (one
    written raw, from the admin or by an older version, may not be)."""
    return isinstance(condition, dict) and all(
        is_path(path)
        and isinstance(comparisons, dict)
        and bool(comparisons)
        and all(operator in OPERATORS for operator in comparisons)
        for path, comparisons in condition.items()
    )


def holds(condition: dict, data: dict) -> bool:
    """Whether every comparison of ``condition`` holds for ``data`` (an empty one always does)."""
    return not failed_clauses(condition, data)


# --- Schedules --------------------------------------------------------------------------------------


def next_fire(schedule: dict, after: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """The first moment of ``schedule`` strictly after ``after``, in ``tz`` (the business's zone)."""
    hour, minute = (int(part) for part in schedule["time"].split(":"))
    local = after.astimezone(tz).replace(tzinfo=None)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    every = schedule["every"]
    if every == "day":
        rule = rrule.rrule(
            rrule.DAILY, dtstart=start, byhour=hour, byminute=minute, bysecond=0
        )
    elif every == "week":
        rule = rrule.rrule(
            rrule.WEEKLY,
            dtstart=start,
            byweekday=schedule["weekday"],
            byhour=hour,
            byminute=minute,
            bysecond=0,
        )
    else:
        rule = rrule.rrule(
            rrule.MONTHLY,
            dtstart=start,
            bymonthday=schedule["day"],
            byhour=hour,
            byminute=minute,
            bysecond=0,
        )
    # Wall clock in the business's zone: 09:00 stays 09:00 across a change of time.
    naive = rule.after(local, inc=False)
    return naive.replace(tzinfo=tz)


# --- Permissions ------------------------------------------------------------------------------------


def required_grants(steps: list[dict]) -> list[str]:
    """The actions, reads and calls' origins the steps need, once each and in order (a half-filled step
    asks nothing)."""
    names: list[str] = []
    for step in steps:
        if step.get("kind") in ("command", "query"):
            name = str(step.get("operation") or "").strip()
            if name and name not in names:
                names.append(name)
        elif step.get("kind") == "http":
            grant = http_grant(str(step.get("url") or ""))
            if grant and grant not in names:
                names.append(grant)
        elif step.get("kind") == "assistant":
            for tool in step.get("tools") or []:
                name = str(tool).strip()
                if name and name not in names:
                    names.append(name)
    return names


# --- Calls to another system (FLOW-F27) ------------------------------------------------------------


def origin(url: str) -> str | None:
    """``https://host[:port]`` of a plain https address (lower case, without the default port), or ``None``."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username is not None or "@" in parts.netloc:
        return None
    host = parts.hostname.lower()
    shown = f"[{host}]" if ":" in host else host
    return f"https://{shown}" if port in (None, 443) else f"https://{shown}:{port}"


def literal_origin(url: str) -> str | None:
    """The origin of ``url`` when its host is written by hand: any ``{{…}}`` goes after it, in the path or
    the query, and cannot change it. ``None`` otherwise."""
    filled = TEMPLATE_RE.sub("x", url)
    found = origin(filled)
    if found is None:
        return None
    if "{{" in url:
        head = url[: url.index("{{")]
        if not re.match(r"^https://[^/?#{}]+[/?#]", head, re.IGNORECASE) or origin(head) != found:
            return None
    return found


def http_grant(url: str) -> str | None:
    """The permission a call to ``url`` asks for (``http:https://host``), or ``None`` for a bad address."""
    found = literal_origin(url)
    return f"{HTTP_GRANT}{found}" if found else None


def host_of(url: str) -> str:
    """The host a call goes to, for the history and the screen."""
    try:
        return (urlsplit(TEMPLATE_RE.sub("x", url)).hostname or "").lower()
    except ValueError:
        return ""


def secret_names(step: Mapping[str, Any]) -> list[str]:
    """The kept secrets a call reads, once each and in order."""
    names: list[str] = []
    for text in (step.get("url", ""), *(step.get("headers") or {}).values(), step.get("body", "")):
        for match in TEMPLATE_RE.finditer(str(text)):
            path = match.group(1)
            if path.startswith("secret.") and CALL_ONLY_RE.match(path) and path[7:] not in names:
                names.append(path[7:])
    return names


def _render(text: str, data: dict, encode) -> str:
    return TEMPLATE_RE.sub(lambda match: encode(_text(lookup(match.group(1), data)[1])), text)


def _json_escaped(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)[1:-1]


def render_call(step: Mapping[str, Any], data: dict, secrets: Mapping[str, str], key: str) -> tuple[str, dict[str, str], str]:
    """``(url, headers, body)`` of a call for what the run knows: a datum inserted in the address is
    percent-encoded, one in a JSON body JSON-escaped, one in a header as it is. A body without its
    ``Content-Type`` gets the JSON one when it looks like JSON, plain text otherwise."""
    full = {**data, "secret": dict(secrets), "run": {"idempotency_key": key}}
    headers = {name: _render(str(value), full, str) for name, value in (step.get("headers") or {}).items()}
    url = _render(str(step.get("url", "")), full, lambda value: quote(value, safe=""))
    body = str(step.get("body") or "")
    kind = next((value for name, value in headers.items() if name.lower() == "content-type"), "")
    if body and not kind:
        kind = "application/json" if body.lstrip().startswith(("{", "[")) else "text/plain; charset=utf-8"
        headers["Content-Type"] = kind
    body = _render(body, full, _json_escaped if "json" in kind.lower() else str)
    return url, headers, body
