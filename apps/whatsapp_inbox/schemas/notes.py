"""Schemas of the internal notes of a conversation."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema

from apps.whatsapp_inbox.schemas.fields import A_NOTE, NOTE, ConversationPageIn, ConversationRefIn, Page, _text


class NoteListIn(ConversationPageIn):
    pass


class NoteAddIn(ConversationRefIn):
    text: _text(5000, 1) = Field(description="The note; the customer never sees it.")


class NoteRefIn(Schema):
    id: UUID = Field(title=NOTE, description="The note's id.", json_schema_extra=A_NOTE)


class NoteOut(Schema):
    id: UUID = Field(description="The note's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    text: str = Field(description="The note.")
    author_id: UUID | None = Field(description="Who wrote it.")
    author_name: str = Field(description="Their name when they wrote it.")
    created_at: datetime = Field(description="When.")
    can_delete: bool = Field(description="Whether the caller may delete it.")


class NotePage(Page[NoteOut]):
    pass


class NoteDeletedOut(Schema):
    id: UUID = Field(description="The deleted note.")
