"""Schemas of the people of the team a conversation can be assigned to."""

from uuid import UUID

from ninja import Field, Schema

from apps.whatsapp_inbox.schemas.fields import Page, PageIn, _text


class AgentListIn(PageIn):
    search: _text(120) | None = Field(
        None, description="Part of the person's name, username or email."
    )


class AgentOut(Schema):
    id: UUID = Field(description="The person's id.")
    name: str = Field(description="Their name.")
    role: str = Field(description="Their role in the business.")


class AgentPage(Page[AgentOut]):
    pass
