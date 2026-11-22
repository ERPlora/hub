"""Schemas of who performs each service: assigning a professional, their own duration and price, and who leaves."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.service.schemas.fields import (
    AN_ASSIGNMENT,
    ASSIGNMENT,
    A_MEMBER,
    A_SERVICE,
    SAY_WHICH_SERVICE,
    ByIdIn,
    Cents,
    In,
    Minutes,
    Page,
    PageIn,
    Said,
    _named,
)

SAY_WHICH_MEMBER = _("Say which professional: their id, or their name.")


class AssignmentListIn(PageIn):
    service_id: UUID | None = Field(
        None, description="Only the professionals of this service."
    )
    service: str | None = Field(
        None,
        max_length=200,
        description="Only the professionals of the service with this name.",
    )
    member_id: UUID | None = Field(
        None, description="Only the services of this professional."
    )
    member: str | None = Field(
        None,
        max_length=200,
        description="Only the services of the professional with this name.",
    )


class EligibleIn(PageIn):
    service_id: UUID | None = Field(None, description="The service, by id.")
    service: Said | None = Field(None, description="The service, by name.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        return self


class AssignIn(In):
    """Assigning someone who already has the service changes their own duration and price."""

    service_id: UUID | None = Field(None, description="The service, by id.", json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description="The service, by name.")
    member_id: UUID | None = Field(None, description="The professional (Staff), by id.", json_schema_extra=A_MEMBER)
    member: Said | None = Field(None, description="The professional (Staff), by name.")
    custom_duration: Minutes | None = Field(
        None, description="Their own duration in minutes; none = the service's."
    )
    custom_price: Cents | None = Field(
        None, description="Their own price in cents (minor units of the business's currency); none = the service's."
    )
    is_primary: bool = Field(
        False, description="Whether it is their main service (one per professional); assigning again without it keeps it."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.service_id, self.service, SAY_WHICH_SERVICE)
        _named(self.member_id, self.member, SAY_WHICH_MEMBER)
        return self


class AssignmentRefIn(ByIdIn):
    id: UUID = Field(title=ASSIGNMENT, description="The id of the record.", json_schema_extra=AN_ASSIGNMENT)


class AssignmentPatchIn(AssignmentRefIn):
    """Only the fields sent change; ``null`` removes an own duration or price."""

    custom_duration: Minutes | None = Field(
        None, description="Own duration in minutes; null = the service's."
    )
    custom_price: Cents | None = Field(
        None, description="Own price in cents (minor units of the business's currency); null = the service's."
    )
    is_primary: bool | None = Field(
        None, description="Make it (true) or stop it being (false) their main service."
    )
    is_active: bool | None = Field(
        None, description="Switch the assignment on (true) or off (false)."
    )


class MemberReleaseIn(In):
    """The payload of ``staff.member.terminated``."""

    id: UUID = Field(description="The professional who left.")


class AssignmentOut(Schema):
    id: UUID
    service_id: UUID
    service_name: str
    member_id: UUID
    member_name: str
    custom_duration: int | None
    custom_price: int | None = Field(json_schema_extra={"money": True})
    is_primary: bool
    is_active: bool
    duration: int = Field(
        description="What it lasts with this professional: their own duration or the service's."
    )
    price: int = Field(
        description="What it costs with this professional: their own price or the service's.",
        json_schema_extra={"money": True},
    )


class AssignmentDetailOut(AssignmentOut):
    label: str = Field(description="How a person tells it apart: the service and the professional, «Haircut · Ana López».")


class EligibleOut(Schema):
    member_id: UUID
    full_name: str
    color: str
    booking_buffer: int
    custom_duration: int | None
    custom_price: int | None = Field(json_schema_extra={"money": True})
    is_primary: bool
    duration: int
    price: int = Field(json_schema_extra={"money": True})


class ReleasedOut(Schema):
    removed: int = Field(description="How many assignments were removed.")


AssignmentPage = Page[AssignmentOut]
EligiblePage = Page[EligibleOut]
