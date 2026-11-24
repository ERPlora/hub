"""The choices of a course: what one is made, changed or put in order with, what a product deleted from the catalogue
takes away, and how one reads back."""

from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.combo.schemas.fields import (
    A_PRODUCT,
    A_PRODUCT_BY_NAME,
    D_DELTA,
    D_PRODUCT,
    D_PRODUCT_ID,
    NEW_PRODUCT,
    SAY_WHICH_PRODUCT,
    Delta,
    OptionIds,
    ProductIds,
    Reference,
    _named,
)
from apps.combo.schemas.references import OptionRefIn, _GroupOfIn
from base.schemas import assistant


class OptionIn(_GroupOfIn):
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID, json_schema_extra=A_PRODUCT)
    product: Reference | None = Field(
        None, description=D_PRODUCT, json_schema_extra=assistant.unless_given(A_PRODUCT_BY_NAME, "product_id")
    )
    price_delta: Delta = Field(0, description=D_DELTA)
    is_available: bool = Field(
        True, description="false: sold out today, kept but not offered."
    )

    @model_validator(mode="after")
    def _named_all(self):
        self._group_named()
        _named(self.product_id, self.product, SAY_WHICH_PRODUCT)
        return self


class OptionBulkIn(_GroupOfIn):
    product_ids: ProductIds = Field(
        title=gettext_noop("Products"),
        description="The products to add, by id, in the order they go in (no supplement).",
    )

    @model_validator(mode="after")
    def _course_named(self):
        self._group_named()
        return self


class OptionPatchIn(OptionRefIn):
    """Only the fields sent change; the choice keeps its position."""

    new_product_id: UUID | None = Field(
        None,
        title=NEW_PRODUCT,
        description="Id of the product that replaces the current one.",
        json_schema_extra=A_PRODUCT,
    )
    new_product: Reference | None = Field(
        None,
        title=NEW_PRODUCT,
        description="SKU or name of the product that replaces the current one.",
        json_schema_extra=assistant.unless_given(A_PRODUCT_BY_NAME, "new_product_id"),
    )
    price_delta: Delta | None = Field(None, description=D_DELTA)
    is_available: bool | None = Field(
        None, description="false: sold out today (not offered); true: back on offer."
    )


class OptionReorderIn(_GroupOfIn):
    option_ids: OptionIds = Field(
        title=gettext_noop("Choices"),
        description="Every choice of the course, by id, in the new order.",
    )

    @model_validator(mode="after")
    def _course_named(self):
        self._group_named()
        return self


class DropProductIn(Schema):
    """The payload of Inventory's ``inventory.product.deleted`` (the rest of it is ignored)."""

    id: UUID = Field(description="The product deleted from the catalogue.")
    sku: str = Field("", title=gettext_noop("SKU"), description="Its SKU, as it was.")
    name: str = Field("", description="Its name, as it was.")


class OptionOut(Schema):
    id: UUID
    group_id: UUID
    product_id: UUID
    product_name: str
    sku: str
    catalog_price: int = Field(
        description="The product's catalogue price, in cents.",
        json_schema_extra={"money": True},
    )
    price_delta: int = Field(json_schema_extra={"money": True})
    is_available: bool
    sort_order: int
    status: Literal[
        "offered", "sold_out", "product_inactive", "product_sold_out", "product_deleted", "not_by_unit", "untaxed"
    ] = Field(
        description="offered; sold_out (marked here); product_inactive, product_sold_out, product_deleted or "
        "not_by_unit (in Inventory); untaxed (no rate to bill it at in a menu to take away)."
    )


class DroppedOut(Schema):
    dropped: int = Field(description="Choices removed.")
