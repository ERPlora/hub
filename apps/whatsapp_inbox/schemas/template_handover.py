"""Schemas of handing a template, or its deletion, to erplora.com for Meta."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema


class ClaimTemplateOut(Schema):
    claimed: bool = Field(description="Whether this hand-over may go now (nobody else on it).")
    template: dict | None = Field(None, description="What goes to erplora.com: the template as door 8 takes it.")
    submit_key: UUID | None = Field(None, description="Its Idempotency-Key.")


class RecordTemplateIn(Schema):
    id: UUID = Field(description="The template handed to erplora.com.")
    submit_key: UUID = Field(description="The key it was handed with: an answer to an older save changes nothing.")
    kind: Literal["accepted", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    meta_id: str = Field("", description="Meta's id, when accepted.")
    status: str = Field("", description="Meta's verdict, when accepted.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="The reason, or what went wrong.")


class ClaimTemplateDeletionOut(Schema):
    claimed: bool = Field(description="Whether Meta still has to delete it (and nobody else is asking).")
    name: str = Field("", description="Its name.")
    language: str = Field("", description="Its language.")
    meta_id: str = Field("", description="Meta's id.")


class RecordTemplateDeletionIn(Schema):
    id: UUID = Field(description="The template deleted here.")
    kind: Literal["accepted", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="The reason, or what went wrong.")
