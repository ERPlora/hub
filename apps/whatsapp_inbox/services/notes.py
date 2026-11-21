"""The team's notes on a conversation (WHATSAPP_INBOX-F36)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events
from apps.whatsapp_inbox.models import Note
from apps.whatsapp_inbox.queries.conversations import find_conversation
from apps.whatsapp_inbox.queries.notes import NOTE_NOT_FOUND, may_delete_note, note_out
from apps.whatsapp_inbox.queries.reads import actor_id, person_name
from apps.whatsapp_inbox.schemas import NoteAddIn, NoteDeletedOut, NoteOut, NoteRefIn
from base.services.sessions import acting_hub_user

NOTE_NOT_YOURS = _("You may only delete your own notes.")


@operation(
    "whatsapp_inbox.note.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=NoteAddIn,
    output=NoteOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add a note to Nuria's chat: call her back after five",
                "leave an internal note on Jorge's conversation",
                "write down on Elena's WhatsApp that she prefers Tuesdays",
            ),
            "es": (
                "añade una nota al chat de Nuria: llamarla después de las cinco",
                "apunta en el WhatsApp de Elena que prefiere los martes",
                "escribe una nota interna en la conversación de Jorge",
            ),
        },
        "description": "Leaves an internal note on a WhatsApp conversation for the team; the customer never sees it.",
        "risk": "normal",
    },
)
def add_note(ctx: OperationContext, data: NoteAddIn) -> dict:
    conversation = find_conversation(ctx, data.id, data.conversation)
    author = acting_hub_user(ctx)
    note = Note.objects.create(
        conversation=conversation,
        text=data.text,
        author=author,
        author_name=person_name(author),
        created_at=clock.now(),
    )
    record_event(
        ctx,
        events.NOTE_ADDED,
        {"id": str(note.id), "conversation_id": str(conversation.id)},
    )
    return note_out(ctx, note, None if author is None else author.pk)


@operation(
    "whatsapp_inbox.note.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=NoteRefIn,
    output=NoteDeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete my note on Nuria's chat",
                "remove the internal note about the deposit",
                "take off the note I left on Jorge's conversation",
            ),
            "es": (
                "borra la nota del chat de Nuria",
                "elimina la nota interna sobre la señal",
                "quita la nota que dejé en la conversación de Jorge",
            ),
        },
        "description": "Deletes an internal note of a WhatsApp conversation: one's own, or anybody's for a manager.",
        "risk": "high",
    },
)
def delete_note(ctx: OperationContext, data: NoteRefIn) -> dict:
    note = (
        Note.objects.select_for_update()
        .filter(pk=data.id, conversation__erased_at__isnull=True)
        .first()
    )
    if note is None:
        raise NotFound(str(NOTE_NOT_FOUND), code="whatsapp_inbox.note_not_found")
    if not may_delete_note(ctx, note, actor_id(ctx)):
        raise PermissionDenied(str(NOTE_NOT_YOURS))
    conversation_id = note.conversation_id
    note.delete()
    record_event(
        ctx,
        events.NOTE_DELETED,
        {"id": str(data.id), "conversation_id": str(conversation_id)},
    )
    return {"id": data.id}
