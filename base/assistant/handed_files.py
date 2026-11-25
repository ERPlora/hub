"""The files a read hands the person in the chat (the CSV or the Excel of an export): the panel offers each to download,
as the screen's button saves it, and the model hears its name.

A read whose output marks the datum that holds its file ``A_HANDED_FILE`` writes a file for the person, not words for
the model: pasted into the answer, the person had to copy it by hand, and the model said it had exported a file the chat
did not give. So the model hears the result without that datum, and the receipt of the read (``executed``) carries the
file to the panel; it never goes to erplora.com, in this round or the next.
"""

import dataclasses
import json

from live import assistant as shared
from live.context import OperationContext
from live.operations import Operation

from base.schemas.assistant import A_HANDED_FILE

from . import tools

#: What the model hears in place of the file (in English, as its instructions).
HANDED = (
    "The file is under your answer, for the person to download with its button: say so, by its name. Never write its "
    "content in the answer."
)
CSV = "text/csv"
#: Excel reads a CSV as UTF-8 only with it, and every export button of the Hub saves a CSV so.
BOM = "﻿"


@dataclasses.dataclass(frozen=True)
class Handed(shared.ToolOutcome):
    """A read's outcome with the file it hands the person: ``filename``, ``content_type`` and ``content``."""

    file: dict


def _datum(op: Operation) -> str | None:
    fields = getattr(op.output, "model_fields", {})
    return next((name for name, field in fields.items() if field.json_schema_extra == A_HANDED_FILE), None)


def run(ctx: OperationContext, op: Operation, arguments: str) -> shared.ToolOutcome:
    """``op`` run for the chat with the model's ``arguments``, as ``tools.run`` runs it; a read that hands a file is told
    to the model without it (``HANDED``), and its outcome carries the file (``Handed``)."""
    datum = _datum(op)
    try:
        data = json.loads(arguments or "{}")
    except ValueError:
        data = None
    if datum is None or not isinstance(data, dict):
        # Arguments that are no object are refused as for any tool.
        return tools.run(ctx, op, arguments)
    failure, result = shared.run(ctx, op, data)
    if failure is not None:
        return failure
    told = result.model_dump(mode="json", exclude={datum})
    content = getattr(result, datum)
    if told.get("content_type") == CSV and not content.startswith(BOM):
        content = BOM + content
    file = {"filename": told.get("filename", ""), "content_type": told.get("content_type", ""), "content": content}
    return Handed("ok", "", json.dumps({**told, "handed": HANDED}, ensure_ascii=False), file)


def receipt(outcome: shared.ToolOutcome) -> dict:
    """What the receipt of a read adds for the panel: the file it handed, if it handed one."""
    return {"file": outcome.file} if isinstance(outcome, Handed) else {}
