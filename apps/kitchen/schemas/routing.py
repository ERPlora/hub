"""The routing: the station each product or category of Inventory goes to."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.kitchen.schemas.fields import (
    A_CATEGORY,
    A_PRODUCT,
    A_STATION,
    SAY_PRODUCT_OR_CATEGORY,
    In,
    Page,
    PageIn,
    Said,
    StationScope,
    _StationNamed,
)


class RoutingListIn(PageIn):
    station: StationScope
    search: str | None = Field(
        None,
        max_length=120,
        description="Part of the product's or the category's name.",
    )


class RouteOut(Schema):
    kind: Literal["product", "category"] = Field(description="A product or a category.")
    target_id: UUID = Field(description="The product's or the category's id.")
    target_name: str = Field(description="Its name.")
    station_id: UUID = Field(description="The station it goes to.")
    station_name: str = Field(description="The station's name.")


RoutingPage = Page[RouteOut]


class _Target(In):
    product_id: UUID | None = Field(None, description="A product of Inventory.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(
        None, description="A product of Inventory by its name."
    )
    category_id: UUID | None = Field(None, description="A category of Inventory.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None, description="A category of Inventory by its name."
    )

    @model_validator(mode="after")
    def _one_target(self):
        product = self.product_id is not None or bool(self.product)
        category = self.category_id is not None or bool(self.category)
        if product == category:
            raise ValueError(str(SAY_PRODUCT_OR_CATEGORY))
        return self


class RoutingSetIn(_StationNamed, _Target):
    station_id: UUID | None = Field(None, description="The station it goes to.", json_schema_extra=A_STATION)
    station: Said | None = Field(None, description="The station by its name.")


class RoutingClearIn(_Target):
    pass
