"""What is new in ERPlora (``base.release_note.list``): the release notes of the version running, in the person's
language."""

from django.utils.translation import get_supported_language_variant
from live.context import OperationContext
from live.operations import AI, operation

from base import release_notes
from base.permissions import VIEW_HOME
from base.release_notes import Note
from base.schemas.release_notes import ReleaseNoteListIn, ReleaseNoteListOut

#: English is the source of every text, and every note says it.
FALLBACK_LANGUAGE = "en"


@operation(
    "base.release_note.list",
    kind="query",
    permission=VIEW_HOME,
    database=False,
    input=ReleaseNoteListIn,
    output=ReleaseNoteListOut,
    ai=AI(
        description=(
            "Lists what is new in ERPlora for this business, newest first: each change it can notice (something new, "
            "an improvement or a fix), the day it arrived, its title and what it lets the person do, in their "
            "language. The hub updates itself, so these are the changes it already has. Pages of up to 100."
        ),
        asks={
            "en": ("what's new in ERPlora?", "what changed in the latest update?"),
            "es": ("¿qué hay de nuevo en ERPlora?", "¿qué ha cambiado en la última actualización?"),
        },
    ),
)
def release_note_list(ctx: OperationContext, data: ReleaseNoteListIn) -> dict:
    """The notes the image ships (``base.release_notes``), anyone's in the business: they say nothing of it."""
    language = _language(ctx.language)
    shipped = release_notes.shipped()
    page = shipped[data.offset : data.offset + data.limit]
    return {"items": [_item(note, language) for note in page], "total": len(shipped)}


def _language(code: str) -> str:
    """The deployment's language ``code`` names (``es-ES`` is ``es``), else English."""
    try:
        return get_supported_language_variant(code)
    except LookupError:
        return FALLBACK_LANGUAGE


def _item(note: Note, language: str) -> dict:
    text = note.texts[language]
    return {"id": note.id, "date": note.date, "kind": note.kind, "title": text.title, "body": text.body}
