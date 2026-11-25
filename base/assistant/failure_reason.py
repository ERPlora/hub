"""Why a write of the assistant failed, said to the person on its receipt (BASE-F97)."""

import json

from django.utils import translation
from django.utils.translation import gettext
from django.utils.translation import gettext_noop as _
from live import assistant as shared
from live.operations import Operation

from .edits import NOTHING_TO_CHANGE

NOT_FITTING = _("The assistant sent data that does not fit.")
NOT_FITTING_NAMED = _("The assistant sent data that does not fit: {names}.")
NOTHING_SAID_TO_CHANGE = _("The assistant did not say what to change.")

#: What the tool itself says to the model when it refuses the data before any app sees them: words for the model,
#: never for the person. The second is live's for arguments that are not a JSON object (``running.run_tool``).
_SAID_TO_THE_MODEL = frozenset({shared.NOT_FITTING, "The arguments are not a JSON object."})


def reason(op: Operation | None, outcome: "shared.ToolOutcome", language: str) -> dict[str, str]:
    """Why ``outcome`` left its write undone, keyed by the language it is said in; ``{}`` unless it failed. An app's
    refusal is its own message, the one its screen shows; data the tool refused before the app saw them (the model's
    slip) are named as the card names each datum, and an edit that named nothing to change says so."""
    if outcome.outcome != "error":
        return {}
    error = json.loads(outcome.content).get("error", {})
    message = str(error.get("message") or "")
    if outcome.code == NOTHING_TO_CHANGE:
        with translation.override(language):
            message = gettext(NOTHING_SAID_TO_CHANGE)
    elif message in _SAID_TO_THE_MODEL:
        with translation.override(language):
            message = _not_fitting(op, error.get("fields") or {})
    return {language: message} if message else {}


def _not_fitting(op: Operation | None, fields: dict) -> str:
    names = _names(op, fields) if op is not None else []
    return gettext(NOT_FITTING_NAMED).format(names=", ".join(names)) if names else gettext(NOT_FITTING)


def _names(op: Operation, fields: dict) -> list[str]:
    """Each datum of ``op``'s input that ``fields`` refuses (``rows.0.price`` is ``rows``), once and in order; what
    is not one of its data (the whole input, ``__all__``) is not named."""
    props = shared.input_schema(op).get("properties", {})
    refused = dict.fromkeys(path.split(".")[0] for path in fields)
    return [shared.label(op, name, props[name].get("title")) for name in refused if name in props]
