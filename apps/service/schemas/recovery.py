"""Schemas of bringing back services and categories of a separate copy of the business."""

from uuid import UUID

from ninja import Field, Schema

from apps.service.schemas.catalog import ServiceIn, ServiceOut
from apps.service.schemas.categories import CategoryIn, CategoryOut
from apps.service.schemas.fields import Cents, In, Minutes
from base.recovery import ImageInCopyIn, RecoveredOut

#: The most professionals a service of a separate copy comes back with.
MAX_PERFORMERS = 500


class AssignmentOfCopyIn(In):
    """A professional who performed a service in a separate copy of the business, as the copy held it."""

    member_id: UUID = Field(description="The professional (Staff), by id: the same in the copy and in the business.")
    custom_duration: Minutes | None = Field(None, description="Their own duration in minutes; none = the service's.")
    custom_price: Cents | None = Field(
        None, description="Their own price in cents (minor units of the business's currency); none = the service's."
    )
    is_primary: bool = Field(False, description="Whether it was their main service.")
    is_active: bool = Field(True, description="Whether the assignment was switched on.")


class ServiceRecoverIn(ServiceIn, ImageInCopyIn):
    """A service of a separate copy the business no longer has: what ``service.service.create`` takes, the image it
    showed there and who performed it there (the business makes its own ids)."""

    assignments: list[AssignmentOfCopyIn] = Field(
        [], max_length=MAX_PERFORMERS, description="Who performed it in the copy."
    )
    stands_for: UUID = Field(description="The service of the copy it is made again for, by its id there.")


class ServiceRecoveredOut(ServiceOut, RecoveredOut):
    """A service made again from a separate copy, and who of those who performed it there it came back without."""


#: The most services of a separate copy another app asks about at once.
MAX_STANDING_FOR = 10_000


class StandingForIn(In):
    """Services of a separate copy of the business, by their ids there."""

    ids: list[UUID] = Field(max_length=MAX_STANDING_FOR, description="The services of the copy, by their ids there.")


class StandingForOut(Schema):
    """The business's service that stands for each of them it no longer holds."""

    standing_for: dict[UUID, UUID] = Field(description="By the id in the copy, the id of the service here.")


#: The most services or subcategories a category of a separate copy takes back.
MAX_INSIDE = 10_000


class CategoryRecoverIn(CategoryIn):
    """A category of a separate copy the business no longer has: what ``service.category.create`` takes and what it
    had inside it there, each by its id, the same in the copy and in the business."""

    stands_for: UUID | None = Field(
        None, description="The category of the copy it comes back for, which the business may still hold deleted."
    )
    service_ids: list[UUID] = Field([], max_length=MAX_INSIDE, description="The services it had inside it.")
    subcategory_ids: list[UUID] = Field([], max_length=MAX_INSIDE, description="The categories that hung from it.")


class CategoryRecoveredOut(CategoryOut, RecoveredOut):
    """A category made again from a separate copy, and what of what it had inside it there it came back without."""


class ServiceLinkIn(In):
    """A service the business kept, and the category a recovery brought back for the one it was in."""

    service_id: UUID = Field(description="The service, the same in the copy and in the business.")
    category_id: UUID = Field(description="The category brought back.")


class SubcategoryLinkIn(In):
    """A subcategory the business kept, and the category a recovery brought back for the one it hung from."""

    category_id: UUID = Field(description="The subcategory, the same in the copy and in the business.")
    parent_id: UUID = Field(description="The category brought back.")
    stands_for: UUID = Field(
        description="The category of the copy it hung from, which the business may still hold deleted."
    )
