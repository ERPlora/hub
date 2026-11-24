"""Schemas of the assistant's drafts (``flow.draft.*``): what it proposes and how a draft reads."""

import datetime as dt
from typing import Annotated, Any
from uuid import UUID

from ninja import Field, Schema
from pydantic import AfterValidator

from apps.flow.schemas.fields import (
    A_DRAFT,
    D_STEPS,
    DraftStatus,
    In,
    Note,
    PageIn,
    Reference,
)
from apps.flow.schemas.steps import DraftStep, _steps
from apps.flow.schemas.triggers import Trigger


class DraftListIn(PageIn):
    pass


class DraftDefinitionIn(In):
    trigger: Trigger | None = Field(
        None, description="When it starts, by its `kind`; none: only by hand."
    )
    steps: Annotated[list[DraftStep], AfterValidator(_steps)] = Field(
        min_length=1,
        max_length=8,
        description="One to eight steps of kind command, condition or delay (never a query). "
        + D_STEPS,
    )


class DraftProposeIn(In):
    name: Reference = Field(
        description="What the owner reads in their list, in their language and words («Call who did not come»)."
    )
    definition: DraftDefinitionIn = Field(
        description="The draft: LINEAR, a condition that does not hold ends the run; no branch, loop or else."
    )
    notes: list[Note] = Field(
        default_factory=list,
        max_length=8,
        description="What you could not work out, one short sentence each, in the owner's language.",
    )


class DraftRefIn(In):
    id: UUID = Field(description="The draft's id.", json_schema_extra=A_DRAFT)


class DraftOut(Schema):
    id: UUID
    name: str
    definition: dict[str, Any]
    notes: list[str]
    status: DraftStatus
    flow_id: UUID | None
    created_at: dt.datetime
    created_by: str
