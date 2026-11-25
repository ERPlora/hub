"""The tax categories products and services link to."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import StringConstraints

from apps.tax.models import CATEGORY_KEY_MAX_LENGTH, CATEGORY_KEY_RE
from apps.tax.schemas.fields import DIRECTION, SEARCH, Direction, OperationClass, Page, PageIn
from apps.tax.schemas.jurisdiction import COUNTRY, REGION, OptionalCountry, OptionalRegion, _RegionOfTheCountry
from apps.tax.schemas.references import CATEGORY_REF, CategoryRef

NewCategoryKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=CATEGORY_KEY_MAX_LENGTH,
        pattern=CATEGORY_KEY_RE,
    ),
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class CategoryListIn(_RegionOfTheCountry, PageIn):
    """The active categories; each row says its rate in force today where ``country_code`` and
    ``region_code`` say."""

    search: str | None = Field(
        None,
        max_length=120,
        description=SEARCH + " Key, name or description, stored or translated.",
    )
    key: str | None = Field(
        None, max_length=CATEGORY_KEY_MAX_LENGTH, description="Part of the key."
    )
    name: str | None = Field(
        None, max_length=255, description="Part of the stored name."
    )
    display_name: str | None = Field(
        None, max_length=255, description="Part of the name as the reader sees it."
    )
    display_description: str | None = Field(
        None,
        max_length=1000,
        description="Part of the description as the reader sees it.",
    )
    is_system: bool | None = Field(
        None, description="True: factory categories only; false: the business's own."
    )
    sort: Literal[
        "key",
        "name",
        "display_name",
        "display_description",
        "is_system",
        "is_active",
        "id",
    ] = Field("key", description="Column to sort by.")
    dir: Direction = Field("asc", description=DIRECTION)
    country_code: OptionalCountry = Field(
        None,
        description=COUNTRY + " Where the rate column is read; empty = the business's country and region.",
    )
    region_code: OptionalRegion = Field(None, description=REGION)


class CategoryGetIn(Schema):
    key: CategoryRef = Field(description=CATEGORY_REF)


class CategoryIn(Schema):
    key: NewCategoryKey = Field(
        description="The key products and services link to; lowercase, starting with a letter; letters, digits, "
        "dots and underscores (product.books). It never changes."
    )
    name: Name = Field(description="The name shown.")
    description: Description = Field("", description="An optional description.")
    is_system: bool = Field(
        False, description="Mark it as a factory category (shown as «System»)."
    )


class CategoryOut(Schema):
    id: UUID = Field(description="The category's id.")
    key: str = Field(description="The key products and services link to.")
    name: str = Field(description="The stored name (English for a factory category).")
    description: str = Field(description="The stored description.")
    display_name: str = Field(description="The name to show, in the reader's language.")
    display_description: str = Field(
        description="The description to show, in the reader's language."
    )
    is_system: bool = Field(
        description="A factory category («System»); otherwise the business's own."
    )
    is_active: bool = Field(description="Active.")


class CategoryNamedOut(CategoryOut):
    label: str = Field(
        description="How a person names the category, in the reader's language: its name and the rate it charges today "
        "in the business's country and region (Restaurant — food · 10%); its name alone without a rule."
    )


class CategoryRowOut(CategoryOut):
    rate_pct: Decimal | None = Field(
        description="The rate in force today where asked, components included; empty without a rule."
    )
    operation_class: OperationClass | None = Field(
        description="Its qualification; empty without a rule."
    )


CategoryPage = Page[CategoryRowOut]
