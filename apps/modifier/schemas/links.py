"""The links of a group: the product or the category it hangs from, said to apply it or let it go, and how one reads
back."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.modifier.schemas.fields import (
    A_CATEGORY,
    A_CATEGORY_BY_NAME,
    A_GROUP,
    A_GROUP_BY_NAME,
    A_LINK,
    A_PRODUCT,
    A_PRODUCT_BY_NAME,
    APPLIES_TO,
    SAY_WHICH_GROUP,
    PageIn,
    Said,
    _Input,
)
from base.schemas.assistant import unless_given

SAY_WHICH_CATEGORY = _("Say which category: its id, or its name.")
SAY_ONE_TARGET = _("Say one product or one category: its id, or its name.")
SAY_WHICH_LINK = _("Say which link: its id, or the group and the product or category.")

TargetKind = Literal["product", "category"]


class LinkListIn(PageIn):
    group_id: UUID | None = Field(None, description="Only the links of this group.")
    group: Said | None = Field(
        None, description="Only the links of the group with this name."
    )
    product_id: UUID | None = Field(None, description="Only the links to this product.")
    category_id: UUID | None = Field(
        None, description="Only the links to this category."
    )


class _Target(_Input):
    product_id: UUID | None = Field(None, description="The product's id.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(
        None,
        description="The product's SKU or name, when its id is not known.",
        json_schema_extra=unless_given(A_PRODUCT_BY_NAME, "product_id"),
    )
    category_id: UUID | None = Field(None, description="The category's id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None,
        description="The category's name, when its id is not known.",
        json_schema_extra=unless_given(A_CATEGORY_BY_NAME, "category_id"),
    )

    def _targets(self) -> int:
        product = self.product_id is not None or self.product is not None
        category = self.category_id is not None or self.category is not None
        return int(product) + int(category)


class LinkIn(_Target):
    group_id: UUID | None = Field(None, description="The group's id.", json_schema_extra=A_GROUP)
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known (e.g. «Sauces»).",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "group_id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.group_id is None and self.group is None:
            raise ValueError(str(SAY_WHICH_GROUP))
        if self._targets() != 1:
            raise ValueError(str(SAY_ONE_TARGET))
        return self


class LinkRefIn(_Target):
    product_id: UUID | None = Field(
        None, description="The product's id.", json_schema_extra=unless_given(A_PRODUCT, "id")
    )
    product: Said | None = Field(
        None,
        description="The product's SKU or name, when its id is not known.",
        json_schema_extra=unless_given(A_PRODUCT_BY_NAME, "id", "product_id"),
    )
    category_id: UUID | None = Field(
        None, description="The category's id.", json_schema_extra=unless_given(A_CATEGORY, "id")
    )
    category: Said | None = Field(
        None,
        description="The category's name, when its id is not known.",
        json_schema_extra=unless_given(A_CATEGORY_BY_NAME, "id", "category_id"),
    )
    id: UUID | None = Field(None, title=APPLIES_TO, description="The link's id.", json_schema_extra=A_LINK)
    group_id: UUID | None = Field(None, description="The group's id.", json_schema_extra=unless_given(A_GROUP, "id"))
    group: Said | None = Field(
        None,
        description="The group's name, when its id is not known.",
        json_schema_extra=unless_given(A_GROUP_BY_NAME, "id", "group_id"),
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and (
            (self.group_id is None and self.group is None) or self._targets() != 1
        ):
            raise ValueError(str(SAY_WHICH_LINK))
        return self


class CategoryRefIn(_Input):
    id: UUID | None = Field(None, description="The category's id.")
    category: Said | None = Field(
        None, description="The category's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


class DropIn(Schema):
    """Inventory's payload of a deleted product or category, as it comes (extra keys are ignored)."""

    id: UUID = Field(description="The id of the deleted product or category.")


class LinkOut(Schema):
    id: UUID = Field(description="The link's id.")
    group_id: UUID = Field(description="The group.")
    group_name: str = Field(description="The group's name.")
    target_kind: TargetKind = Field(description="product or category.")
    product_id: UUID | None = Field(description="The product, when it hangs from one.")
    product_name: str | None = Field(description="The product's name.")
    product_sku: str | None = Field(description="The product's SKU.")
    category_id: UUID | None = Field(
        description="The category, when it hangs from one."
    )
    category_name: str | None = Field(description="The category's name.")
    created_at: datetime = Field(description="When it was linked.")


class LinkDetailOut(LinkOut):
    label: str = Field(description="How a person tells it apart: its group and what it hangs from, «Sauces · Burger».")


class CategoryRefOut(Schema):
    id: UUID = Field(description="The category's id.")
    name: str = Field(description="Its name, as Inventory shows it.")


class DropOut(Schema):
    dropped: int = Field(description="How many links were dropped.")
