"""A key the assistant would write as it is in a call's headers (``flow.flow.check``, FLOW-F26).

Creating or changing an automation names this read as its check, so the Hub runs it before the assistant's card and
only for the assistant: a key told in the chat never ends up written in a step. A person typing a header on the screen
or by the API is not checked.
"""

import re

from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import INTERNAL, operation

from apps.flow import document
from apps.flow.schemas.fields import KEY_IN_STEP
from apps.flow.schemas.flows import CheckIn, CheckOut

from .reads import MANAGE

KEY_IN_STEP_CODE = "flow.key_in_step"
#: The headers that carry a credential: HTTP's own (``Authorization``) and the usual ones of an API key or a token.
CREDENTIAL_HEADER = re.compile(r"auth|api[-_]?key|token|secret|passw", re.IGNORECASE)
#: The scheme a credential may start with («Bearer », «Basic »), followed by the credential itself.
SCHEME = re.compile(r"^\s*[A-Za-z][A-Za-z0-9-]*\s+")
LETTER_OR_DIGIT = re.compile(r"[A-Za-z0-9]")


def written_out(name: str, value: str) -> bool:
    """Whether header ``name`` carries a credential written as it is, not only its scheme and ``{{…}}`` data."""
    if not CREDENTIAL_HEADER.search(name):
        return False
    credential = SCHEME.sub("", value, count=1)
    return LETTER_OR_DIGIT.search(document.TEMPLATE_RE.sub("", credential)) is not None


@operation(
    "flow.flow.check",
    kind="query",
    permission=MANAGE,
    input=CheckIn,
    output=CheckOut,
    ai=INTERNAL,
)
def check_calls(ctx: OperationContext, data: CheckIn) -> dict:
    """Refuses, by step, a call whose headers hold a key written as it is; no route and no assistant tool."""
    calls = [(index, step) for index, step in enumerate(data.steps or []) if step.kind == "http"]
    problems: dict[str, str] = {}
    for index, step in calls:
        named = next((name for name, value in step.headers.items() if written_out(name, value)), None)
        if named is not None:
            problems[f"steps.{index}.headers"] = str(KEY_IN_STEP) % {"name": named}
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=KEY_IN_STEP_CODE, fields=problems)
    return {"calls": len(calls)}
