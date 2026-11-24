"""The files the person attaches in the assistant's chat, which a tool can take whole: a copy of a business
(``.blueprint.zip``), or a document or a photo kept in Files.

erplora.com reads images and documents for the model, but the model gets neither their names nor their bytes, and a
file for a tool (``TOOL_TYPES``) is never read there. So each file reaches the gateway with its name (``for_gateway``):
one it reads named before it, one for a tool by its name alone. The model gives that name in the datum its tool marks
``AN_ATTACHED_FILE``, and the turn gives the operation the file the person attached (``with_files``). The panel keeps a
file attached before the page reloaded by its name alone: then nothing runs and the model hears it must be attached
again.
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
#: What the model hears before a file it reads, whose name the gateway does not give it.
NAMED = "[Attachment: «{name}»] Give its name, «{name}», where a tool asks for an attached file."
#: The parts of a message that carry a file, as the panel attaches them: a photo, or any other file.
FILE_PARTS = frozenset({"image_url", "input_file"})


def _files(message: dict) -> list[dict]:
    content = message.get("content")
    parts = content if isinstance(content, list) else []
    return [part for part in parts if isinstance(part, dict) and part.get("type") in FILE_PARTS]


def _base64(part: dict) -> str | None:
    """The base64 a file part carries: a photo's inside its data address."""
    if part.get("type") == "input_file":
        data = part.get("data")
        return data if isinstance(data, str) else None
    url = part.get("image_url", {}).get("url") if isinstance(part.get("image_url"), dict) else None
    return url.split(",", 1)[1] if isinstance(url, str) and url.startswith("data:") and "," in url else None


def attached(messages: list[dict]) -> dict[str, str]:
    """The files the person attached in ``messages``, in base64 by their names; of two with one name, the later."""
    files: dict[str, str] = {}
    for message in messages:
        for part in _files(message) if message.get("role") == "user" else []:
            data = _base64(part)
            if part.get("filename") and data is not None:
                files[str(part["filename"])] = data
    return files


def _said(part) -> list:
    if not isinstance(part, dict) or part.get("type") not in FILE_PARTS:
        return [part]
    name = part.get("filename") or ""
    if part.get("type") == "input_file" and part.get("mime_type") in TOOL_TYPES:
        return [{"type": "text", "text": FOR_A_TOOL.format(name=name)}]
    if part.get("type") == "image_url":
        # erplora.com takes a photo as its providers do, without the name the panel sends beside it.
        part = {"type": "image_url", "image_url": part.get("image_url")}
    return [{"type": "text", "text": NAMED.format(name=name)}, part] if name else [part]


def for_gateway(messages: list[dict]) -> list[dict]:
    """``messages`` as they go to the gateway: each file named before it, and one for a tool by its name alone."""
    return [
        {**message, "content": [said for part in message["content"] for said in _said(part)]}
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
