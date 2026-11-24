"""The files the person attaches in the chat that a tool takes whole (a copy of a business, ``.blueprint.zip``).

erplora.com reads images and documents for the model; a file for a tool is never read there, and the model could not
copy its bytes into a call. So it reaches the gateway by its name alone (``for_gateway``), the model gives that name in
the datum its tool marks ``AN_ATTACHED_FILE``, and the turn gives the operation the file the person attached
(``with_files``). The panel keeps a file attached before the page reloaded by its name alone: then nothing runs and the
model hears it must be attached again.
"""

from django.utils import translation
from django.utils.translation import gettext
from django.utils.translation import gettext_noop as _
from live import assistant as shared

from base.schemas.assistant import AN_ATTACHED_FILE

#: The types of file a tool takes whole, as the panel attaches them (``toolFiles`` of base/frontend/lib/assistant-hub.ts).
TOOL_TYPES = frozenset({"application/zip"})
MISSING = "base.assistant_attachment_missing"
NOT_ATTACHED = _("There is no file «{name}» attached to this conversation: attach it again.")
#: What the model hears in place of a file for a tool (in English, as its instructions).
FOR_A_TOOL = (
    "[Attachment: «{name}»] A file for a tool, which takes it whole: it is not read here. Give its name, «{name}», "
    "where a tool asks for an attached file."
)


def _files(message: dict) -> list[dict]:
    content = message.get("content")
    parts = content if isinstance(content, list) else []
    return [part for part in parts if isinstance(part, dict) and part.get("type") == "input_file"]


def attached(messages: list[dict]) -> dict[str, str]:
    """The files the person attached in ``messages``, in base64 by their names; of two with one name, the later."""
    return {
        str(part["filename"]): part["data"]
        for message in messages
        if message.get("role") == "user"
        for part in _files(message)
        if part.get("filename") and isinstance(part.get("data"), str)
    }


def _said(part):
    if isinstance(part, dict) and part.get("type") == "input_file" and part.get("mime_type") in TOOL_TYPES:
        return {"type": "text", "text": FOR_A_TOOL.format(name=part.get("filename") or "")}
    return part


def for_gateway(messages: list[dict]) -> list[dict]:
    """``messages`` as they go to the gateway: each file for a tool by its name alone; the rest as they are."""
    return [
        {**message, "content": [_said(part) for part in message["content"]]}
        if isinstance(message.get("content"), list)
        else message
        for message in messages
    ]


def with_files(op, arguments: dict, files: dict[str, str], language: str):
    """``(arguments, None)`` with each datum of ``op`` marked ``AN_ATTACHED_FILE`` holding the file it names, or
    ``(None, refusal)`` when it names none of ``files``: an error said in ``language``, as an app says its refusals."""
    given = dict(arguments)
    for name, field in op.input.model_fields.items():
        said = arguments.get(name)
        if field.json_schema_extra != AN_ATTACHED_FILE or not said:
            continue
        if said not in files:
            with translation.override(language):
                message = gettext(NOT_ATTACHED).format(name=said)
            return None, shared.ToolOutcome("error", MISSING, shared.error_content(MISSING, message))
        given[name] = files[said]
    return given, None
