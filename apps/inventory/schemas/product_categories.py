"""Schemas of the links between a product and its categories."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.inventory.schemas.fields import A_CATEGORY, SAY_WHICH_CATEGORY, Page, PageIn, Said, _ProductLineRef


class ProductCategoryListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the product's name or SKU, or of the category's name.",
    )
    product_id: UUID | None = Field(
        None, description="Only the categories of this product."
    )
    category_id: UUID | None = Field(
        None, description="Only the products of this category."
    )


class ProductCategoryIn(_ProductLineRef):
    category_id: UUID | None = Field(None, description="The category's id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None, description="The category's name or slug, when its id is not known."
    )

    @model_validator(mode="after")
    def _category_named(self):
        if self.category_id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


class ProductCategoryOut(Schema):
    product_id: UUID = Field(description="The product.")
    category_id: UUID = Field(description="One of its categories.")


ProductCategoryPage = Page[ProductCategoryOut]


class ProductCategoryLinkOut(ProductCategoryOut):
    changed: bool = Field(
        description="False when nothing changed (the link was already there, or was not)."
    )
