"""Schemas of the copies of the business's data (``base.hub.dumps``, ``base.hub.dump_list``, ``base.hub.dump_link``)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field

from base.schemas.blueprints import RemovalOut


class HubDumpsIn(Schema):
    """No input: the copies of the business of the request."""


class ResetSectionNameOut(Schema):
    id: str
    label: str


class ResetStateOut(Schema):
    """How the last reset of the business went (``Hub.reset_sections``): asked, copying, emptying, done or failed."""

    state: Literal["copying", "emptying", "done", "failed"]
    sections: list[ResetSectionNameOut] = Field(description="The sections asked, by name.")
    requested_by: str
    error: str = Field(
        description="Why it failed: dumps_unavailable, dump_failed, emptying_failed or hub_not_ready; empty otherwise."
    )
    removed: list[RemovalOut] = Field(description="What was removed of each section (done).")
    finished_at: dt.datetime | None


class HubDumpOut(Schema):
    id: UUID
    kind: Literal["reset", "offboarding"]
    created_at: dt.datetime
    bytes: int


class HubDumpsOut(Schema):
    """``base.hub.dumps``: the copies of the business's data (newest first) and its last reset."""

    available: bool = Field(
        description="False while the business shares its database with others: no copy is ever made then."
    )
    reset: ResetStateOut | None
    dumps: list[HubDumpOut]


class HubDumpLinkIn(Schema):
    id: UUID = Field(description="The copy's id (base.hub.dumps).")


class HubDumpLinkOut(Schema):
    url: str = Field(description="A link that downloads the copy, for 15 minutes.")
    expires_at: dt.datetime


class InternalDumpOut(Schema):
    id: str = Field(description="Its key in the bucket.")
    kind: Literal["reset", "offboarding"]
    created_at: dt.datetime
    bytes: int
    url: str


class InternalDumpsOut(Schema):
    """``GET /internal/hubs/{id}/dumps`` (saas ``hubs/README.md``, «Contrato para el Hub»)."""

    available: bool
    dumps: list[InternalDumpOut]

