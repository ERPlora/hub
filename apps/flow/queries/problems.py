"""Why a document cannot be saved: what it names that this business does not have, has turned off or may
not leave to an automation, by field."""

from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import Scope

from apps.flow import document
from base import assistant as hub_assistant
from apps.flow.models import Secret

from .catalog import (
    asks_first,
    catalog_events,
    _events_of,
    _grantable_of,
    grantable_operations,
    installed_apps,
    needs_a_person,
)
from .pinned import pinned_problem

UNKNOWN_EVENT = _("That does not happen in this business: «%(name)s».")
UNKNOWN_ACTION = _("That action does not exist in this business: «%(name)s».")
#: Off is not «does not exist» (hub#1054): what is missing is of an app the business turned off, and it comes back on.
OFF_EVENT = _(
    "«%(name)s» is from %(app)s, which is off in this business: turn it on in Apps, or choose another event."
)
OFF_ACTION = _(
    "«%(name)s» is from %(app)s, which is off in this business: turn it on in Apps, or choose another action."
)
NOT_AN_ACTION = _("«%(name)s» only reads: use «Look something up».")
NOT_A_READ = _("«%(name)s» changes data: use «Do something».")
HIGH_RISK = _("«%(name)s» needs a person in front: an automation cannot do it.")
ASK_FIRST_ONLY = _("«%(name)s» needs a person's yes first: choose «Ask me first».")
#: The code of a refusal of an action that needs a person, when it is saved, granted or run.
HIGH_RISK_CODE = "flow.high_risk"
NO_SECRET = _("There is no secret called «%(name)s».")
BAD_HTTP_GRANT = _("«%(name)s» is no address this automation can be allowed to call.")
NOT_FOR_THE_ASSISTANT = _("The assistant cannot use «%(name)s».")


def _app_name(label: str) -> str:
    return str(installed_apps()[label].verbose_name)


def operation_problem(  # noqa: PLR0911
    scope: Scope, name: str, kind: str | None = None, *, asking: bool = False
) -> tuple[str, str] | None:
    """``(code, message)`` of why an automation may not run the operation ``name`` (as a step of
    ``kind``, when given; for a step that asks first, ``asking``), or ``None`` when it may. A call's origin
    (``http:https://host``) is checked as an address."""
    if name.startswith(document.HTTP_GRANT) and kind is None:
        address = name[len(document.HTTP_GRANT) :]
        if document.origin(address) != address:
            return "invalid_payload", str(BAD_HTTP_GRANT) % {"name": name}
        return None
    op = grantable_operations(scope).get(name)
    if op is None:
        off = _grantable_of(installed_apps()).get(name)
        if off is not None:
            return "invalid_payload", str(OFF_ACTION) % {"name": name, "app": _app_name(off.app_label)}
        return "invalid_payload", str(UNKNOWN_ACTION) % {"name": name}
    if needs_a_person(op) and not (asking and asks_first(op)):
        message = ASK_FIRST_ONLY if kind is None and asks_first(op) else HIGH_RISK
        return HIGH_RISK_CODE, str(message) % {"name": name}
    if kind == "command" and op.kind != "command":
        return "invalid_payload", str(NOT_AN_ACTION) % {"name": name}
    if kind == "query" and op.kind != "query":
        return "invalid_payload", str(NOT_A_READ) % {"name": name}
    return None


def catalog_problems(scope: Scope, trigger: Any, steps: list[Any]) -> tuple[dict[str, str], str]:  # noqa: C901, PLR0912
    """What a document names that this business does not have, by field (``trigger.event``,
    ``steps.<n>.operation``), and the code of the refusal: ``flow.high_risk`` when a step needs a
    person in front, ``invalid_payload`` otherwise."""
    problems: dict[str, str] = {}
    code = "invalid_payload"
    if trigger is not None and trigger.kind == "event" and trigger.event not in catalog_events(scope):
        off = _events_of(installed_apps()).get(trigger.event)
        problems["trigger.event"] = (
            str(OFF_EVENT) % {"name": trigger.event, "app": str(off.verbose_name)}
            if off is not None
            else str(UNKNOWN_EVENT) % {"name": trigger.event}
        )
    kept = None
    for index, step in enumerate(steps):
        if step.kind == "http":
            # A call names kept secrets: each must exist (FLOW-F26), named next to the field that reads it.
            kept = set(Secret.objects.values_list("name", flat=True)) if kept is None else kept
            for name in document.secret_names(step.model_dump()):
                if name not in kept:
                    field = next(
                        part
                        for part, text in (("url", step.url), ("headers", " ".join(step.headers.values())), ("body", step.body))
                        if f"secret.{name}" in text
                    )
                    problems.setdefault(f"steps.{index}.{field}", str(NO_SECRET) % {"name": name})
            continue
        if step.kind == "assistant":
            for name in step.tools:
                problem = operation_problem(scope, name, asking=step.mode == "ask")
                if problem is None and not hub_assistant.tools.is_tool(grantable_operations(scope)[name]):
                    problem = ("invalid_payload", str(NOT_FOR_THE_ASSISTANT) % {"name": name})
                if problem is not None:
                    problem_code, problems[f"steps.{index}.tools"] = problem
                    code = HIGH_RISK_CODE if problem_code == HIGH_RISK_CODE else code
                    break
            problem = pinned_problem(scope, step.tools, step.pinned or {})
            if problem is not None:
                problems[f"steps.{index}.pinned"] = problem
            continue
        if step.kind not in ("command", "query"):
            continue
        problem = operation_problem(scope, step.operation, step.kind)
        if problem is not None:
            problem_code, problems[f"steps.{index}.operation"] = problem
            if problem_code == HIGH_RISK_CODE:
                code = HIGH_RISK_CODE
    return problems, code
