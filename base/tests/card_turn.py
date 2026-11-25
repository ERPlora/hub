"""A turn of the assistant in which the model asked for one write: the card it draws, or what the person's answer to it
runs."""

import json

from django.utils import translation
from live import assistant as shared
from live.context import OperationContext
from live.operations import get


def call(name: str, arguments: dict) -> dict:
    """The write the model asks for, as it waits for its card."""
    return {"call_id": "c1", "name": shared.tool_name(name), "arguments": json.dumps(arguments)}


def turn(context: OperationContext, pending: dict, *, said: str, decision: dict | None = None) -> dict:
    """The turn of ``context``'s person, who ``said`` it, with ``pending`` waiting; in their language, as the request's
    middleware turns it on."""
    function = {"name": pending["name"], "arguments": pending["arguments"]}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": pending["call_id"], "type": "function", "function": function}],
    }
    op = get("base.assistant.turn")
    messages = [{"role": "user", "content": said}, asked]
    data = op.input.model_validate({"messages": messages, "pending": [pending], "decision": decision})
    with translation.override(context.language):
        return op(context, data).model_dump(mode="json")
