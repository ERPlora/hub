"""Schemas of what a price list, a price or a rule points at in another app (``pricing.catalog.get``), and of the
events of those apps that the pricing app reacts to."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, model_validator

from apps.pricing.schemas.fields import D_SERVICE_ID, In

ONE_RECORD = _("Say one service, one category or one customer group, by its id.")


# What a price or a rule points at in another app (the assistant's card names it by this read)


class CatalogRefIn(In):
    """One record of another app a price list, a price or a rule points at, by its id: exactly one."""

    service_id: UUID | None = Field(None, description=D_SERVICE_ID)
    category_id: UUID | None = Field(None, description="The category's id (Inventory).")
    customer_group_id: UUID | None = Field(None, description="The customer group's id (Customers).")

    @model_validator(mode="after")
    def _one(self) -> "CatalogRefIn":
        if sum(value is not None for value in (self.service_id, self.category_id, self.customer_group_id)) != 1:
            raise ValueError(str(ONE_RECORD))
        return self


class CatalogRecordOut(Schema):
    id: UUID = Field(description="Its id.")
    name: str = Field(description="Its name, as its own app says it.")


# Reactions to other apps' events


class CatalogEventIn(Schema):
    """The payload of ``inventory.product.deleted``, ``inventory.category.deleted``,
    ``customer.group.deleted`` or ``service.service.updated``: only its id is read."""

    model_config = ConfigDict(extra="ignore")

    id: UUID = Field(description="The id of the product, category, group or service of the event.")


class CatalogOut(Schema):
    lists: int = Field(description="Price lists changed.")
    items: int = Field(description="Prices removed or changed.")
    rules: int = Field(description="Rules switched off or changed.")
