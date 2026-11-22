"""The team's notes on a conversation: who may delete one, their list and one note."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.whatsapp_inbox.models import Note
from apps.whatsapp_inbox.queries.conversations import find_conversation
from apps.whatsapp_inbox.queries.reads import actor_id, page
from apps.whatsapp_inbox.schemas.notes import NoteListIn, NoteOut, NotePage, NoteRefIn

NOTE_NOT_FOUND = _("That note no longer exists.")


def may_delete_note(ctx: OperationContext, note: Note, me: UUID | None) -> bool:
    """The author deletes their own note; whoever may assign deletes anybody's. ``me`` is the caller's person
    (:func:`actor_id`), read once by whoever asks about several notes."""
    mine = note.author_id is not None and note.author_id == me
    return mine or ctx.has("whatsapp_inbox.assign")


def note_out(ctx: OperationContext, row: Note, me: UUID | None) -> dict:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "text": row.text,
        "author_id": row.author_id,
        "author_name": row.author_name,
        "created_at": row.created_at,
        "can_delete": may_delete_note(ctx, row, me),
    }


@operation(
    "whatsapp_inbox.note.list",
    kind="query",
    permission="whatsapp_inbox.view",
    input=NoteListIn,
    output=NotePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what notes does Nuria's conversation have?",
                "show me the internal notes on Jorge's chat",
                "did anyone leave a note on this WhatsApp?",
            ),
            "es": (
                "¿qué notas tiene la conversación de Nuria?",
                "enséñame las notas internas del chat de Jorge",
                "¿alguien dejó una nota en este WhatsApp?",
            ),
        },
        "description": "The internal notes of a WhatsApp conversation, newest first: what the team wrote about it."
    },
)
def list_notes(ctx: OperationContext, params: NoteListIn) -> dict:
    conversation = find_conversation(ctx, params.id, params.conversation)
    rows = Note.objects.filter(conversation=conversation).order_by("-created_at", "-id")
    me = actor_id(ctx)
    return page(rows, params, lambda note: note_out(ctx, note, me))


# Not an assistant tool: what names a note on the card of ``whatsapp_inbox.note.delete`` (``schemas.fields.A_NOTE``),
# by its text; the model finds the notes of a conversation in their list.
@operation(
    "whatsapp_inbox.note.get",
    kind="query",
    permission="whatsapp_inbox.view",
    input=NoteRefIn,
    output=NoteOut,
    ai=INTERNAL,
)
def get_note(ctx: OperationContext, data: NoteRefIn) -> dict:
    note = Note.objects.filter(pk=data.id, conversation__erased_at__isnull=True).first()
    if note is None:
        raise NotFound(str(NOTE_NOT_FOUND), code="whatsapp_inbox.note_not_found")
    return note_out(ctx, note, actor_id(ctx))
