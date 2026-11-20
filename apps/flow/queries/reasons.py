"""Why a run stopped, said when it is read, in the reader's language (FLOW-F16), and an action as the
History names it (``flow.operation.get``)."""

import functools
import json
from pathlib import Path

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, Operation, operation, registry

from base import assistant as hub_assistant
from apps.flow.schemas.catalog import OperationNameOut, OperationRefIn

from .problems import HIGH_RISK, HIGH_RISK_CODE, UNKNOWN_ACTION
from .reads import VIEW

NOT_ALLOWED = _(
    "It tried to do something you have not allowed it to do («%(name)s»), so it stopped. "
    "Open Permissions and allow what it needs."
)
UNAVAILABLE = _(
    "«%(name)s» is not available in this business any more (its app is off), so it stopped."
)
INVALID_PARAMS = _("«%(name)s» did not accept the data it was given, so it stopped.")
CRASHED = _(
    "Something went wrong while doing «%(name)s», so it stopped. Nothing of that step was kept."
)
LOOP = _(
    "It was started by something its own steps did, so it stopped before doing anything."
)
CHAIN_TOO_LONG = _(
    "A chain of %(count)s automations started it, more than the %(max)s allowed, so it stopped before doing "
    "anything."
)
FILTER_UNREADABLE = _(
    "Its «Only when…» can no longer be read, so it did not go on. Open it, check «Only when…» and save it "
    "again."
)
CONDITION_UNREADABLE = _(
    "This «Only continue if…» can no longer be read, so it stopped. Open the automation, check this step "
    "and save it again."
)
RUN_IF_UNREADABLE = _(
    "The «Only if…» of this step can no longer be read, so it stopped. Open the automation, check this step "
    "and save it again."
)
HTTP_STATUS = _("«%(host)s» answered %(status)s, so it stopped.")
HTTP_BLOCKED = _("«%(host)s» is inside a private network, so it was not called.")
HTTP_FAILED = _("It could not reach «%(host)s», so it stopped.")
HTTP_TIMEOUT = _("«%(host)s» did not answer within %(seconds)s seconds, so it stopped.")
HTTP_INVALID = _("The address of this step is not a plain https address, so it was not called.")
SECRET_GONE = _(
    "The secret «%(name)s» no longer exists, so it stopped before calling. Save it again in this step."
)
SECRET_UNREADABLE = _(
    "The secret «%(name)s» cannot be opened with this server's key, so it stopped before calling. Save it "
    "again in this step."
)
SECRETS_KEY_GONE = _(
    "This server cannot use secrets (its encryption key is missing), so it stopped before calling."
)
CANCELLED_PAUSED = _("Cancelled: the automation was paused while it waited.")
CANCELLED_DELETED = _("Cancelled: the automation was deleted.")
CANCELLED_ERASED = _("Cancelled: the customer's personal data were erased.")
ANSWERED_NO = _("Cancelled: %(who)s answered no to «%(title)s».")
NOBODY_ANSWERED = _("Cancelled: nobody answered «%(title)s» in time.")
ASSISTANT_ROUNDS = _("The assistant took its %(n)s turns without finishing, so it stopped.")
ASSISTANT_QUOTA = _(
    "The assistant's messages of this month are spent, so it stopped. They come back on the 1st; for more, "
    "upgrade the plan."
)
ASSISTANT_UNAVAILABLE = _("The assistant could not answer now, so it stopped: resume the run in a while.")
ASSISTANT_UNREACHABLE = _("It could not reach the assistant on erplora.com, so it stopped: resume the run in a while.")
ASSISTANT_REFUSED = _("erplora.com's assistant did not take the task, so it stopped.")
ASSISTANT_GONE = _("«%(name)s» is no longer allowed or available, so the assistant's change was not made.")
ASSISTANT_GONE_UNNAMED = _("That action is no longer allowed or available, so the assistant's change was not made.")

#: A change of the assistant no longer granted (code ``flow.not_allowed``), named for a person when it is read.
ASSISTANT_GONE_KEY = "flow.assistant_gone"
#: The reasons of a question nobody said yes to that, for the assistant's change, name its action (``say``).
NAMED_BY_ITS_ACTION = frozenset({"flow.question_rejected", "flow.question_expired"})
#: The engine's own reasons, by name (the code, but where one code says different things): a run and the entry of
#: the step that failed keep the name and its values, and the reason is said when it is read, in the reader's
#: language (FLOW-F16). A name never equals a code it does not say whole: a run kept with its words alone
#: (before names were kept) is said by its code (``say``).
REASONS = {
    HIGH_RISK_CODE: HIGH_RISK,
    "flow.not_allowed": NOT_ALLOWED,
    "flow.action_unavailable": UNAVAILABLE,
    "flow.invalid_params": INVALID_PARAMS,
    "flow.step_crashed": CRASHED,
    "flow.loop": LOOP,
    "flow.chain_too_long": CHAIN_TOO_LONG,
    "flow.filter_unreadable": FILTER_UNREADABLE,
    "flow.condition_unreadable": CONDITION_UNREADABLE,
    "flow.run_if_unreadable": RUN_IF_UNREADABLE,
    "flow.http_status": HTTP_STATUS,
    "flow.http_blocked": HTTP_BLOCKED,
    "flow.http_failed": HTTP_FAILED,
    "flow.http_timeout": HTTP_TIMEOUT,
    "flow.http_url_invalid": HTTP_INVALID,
    "flow.secret_not_found": SECRET_GONE,
    "flow.secret_unreadable": SECRET_UNREADABLE,
    "flow.secrets_key_missing": SECRETS_KEY_GONE,
    "flow.paused": CANCELLED_PAUSED,
    "flow.deleted": CANCELLED_DELETED,
    "flow.customer_erased": CANCELLED_ERASED,
    "flow.question_rejected": ANSWERED_NO,
    "flow.question_expired": NOBODY_ANSWERED,
    "flow.assistant_too_many_rounds": ASSISTANT_ROUNDS,
    "flow.assistant_quota_exceeded": ASSISTANT_QUOTA,
    "flow.assistant_unavailable": ASSISTANT_UNAVAILABLE,
    "flow.assistant_unreachable": ASSISTANT_UNREACHABLE,
    "flow.assistant_refused": ASSISTANT_REFUSED,
    ASSISTANT_GONE_KEY: ASSISTANT_GONE,
}
#: The words of the app's screens, by language: how the History names an action («Create a task»).
LOCALES = Path(__file__).resolve().parent.parent / "frontend" / "locale"


@functools.cache
def _screen_words(language: str) -> dict:
    path = LOCALES / f"{language}.json"
    return json.loads((path if path.exists() else LOCALES / "en.json").read_text(encoding="utf-8"))["flow"]


def action_label(op: Operation, language: str) -> str:
    """``op`` as the History names it: its own words or, without them, its verb, app and thing (``actionLabel`` of
    ``frontend/lib/phrasing.ts``)."""
    words = _screen_words(language)
    curated = words["actions"].get(op.name.replace(".", "__"))
    if curated:
        return curated
    _app, entity, verb = ([*op.name.split(".", 2), "", ""])[:3]
    verb_word = words["verbs"].get(verb) or verb.replace("_", " ")
    return f"{verb_word} · {hub_assistant.cards.app_name(op)} ({entity.replace('_', ' ')})"


@operation(
    "flow.operation.get",
    kind="query",
    permission=VIEW,
    input=OperationRefIn,
    output=OperationNameOut,
    ai=INTERNAL,
)
def operation_name(ctx: OperationContext, data: OperationRefIn) -> dict:
    """The label of a permission on a grant's card, as the History names that operation; no route and no assistant tool."""
    op = registry.get(data.operation)
    if op is None:
        raise NotFound(str(UNKNOWN_ACTION) % {"name": data.operation})
    return {"operation": op.name, "label": action_label(op, ctx.language)}


def say(reason: dict, said: str = "") -> str:
    """Why a run (or its step) stopped, in the active language: the engine's own words for a reason it named
    (``{"key", "values"}``); ``said`` — what an action of another app answered, as it answered, or a reason kept
    before its values were — for anything else."""
    key = reason.get("key")
    words = REASONS.get(key)
    if words is None:
        return said
    values = dict(reason.get("values") or {})
    if key == ASSISTANT_GONE_KEY:
        # The action it wanted, named as the History names it now; one that no longer exists, not at all.
        op = registry.get(str(values.get("operation", "")))
        if op is None:
            return str(ASSISTANT_GONE_UNNAMED)
        values["name"] = action_label(op, (translation.get_language() or "en").split("-")[0])
    elif key in NAMED_BY_ITS_ACTION and values.get("operation"):
        # The assistant's change nobody said yes to, by its action as the History names it now («Cancel a
        # reservation»), not by the title kept in the automation's language; one that no longer exists, by that title.
        op = registry.get(str(values["operation"]))
        if op is not None:
            values["title"] = action_label(op, (translation.get_language() or "en").split("-")[0])
    try:
        return str(words) % values
    except (KeyError, TypeError, ValueError):
        return said


def _said_entry(entry: dict) -> dict:
    """A log entry with the reason of its failure, if any, in the active language (its name stays inside)."""
    error = entry.get("error")
    if not isinstance(error, dict):
        return entry
    shown = {name: value for name, value in error.items() if name != "reason"}
    shown["message"] = say(error.get("reason") or {"key": error.get("code")}, error.get("message", ""))
    return {**entry, "error": shown}
