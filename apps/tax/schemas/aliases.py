"""The aliases of the tax categories: the outside texts read as a category (TAX-F13)."""

from typing import Annotated, Any, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import BeforeValidator, StringConstraints

from apps.tax.models import CATEGORY_KEY_MAX_LENGTH, TaxAlias
from apps.tax.schemas.fields import DIRECTION, SEARCH, Direction, Page, PageIn
from apps.tax.schemas.references import A_TAX_CATEGORY, CATEGORY, CATEGORY_REF, CategoryRef


def normalize_text(text: str) -> str:
    """How an outside text is compared: lowercase, single spaces, no spaces at the ends."""
    return " ".join(text.split()).lower()


def _normalized(value: Any) -> Any:
    return normalize_text(value) if isinstance(value, str) else value


AliasText = Annotated[
    str, StringConstraints(min_length=1, max_length=200), BeforeValidator(_normalized)
]

AliasSource = Literal[*TaxAlias.Source.values]


class AliasListIn(PageIn):
    """The active aliases."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Alias or category key."
    )
    alias: str | None = Field(None, max_length=200, description="Part of the alias.")
    tax_category_key: str | None = Field(
        None,
        max_length=CATEGORY_KEY_MAX_LENGTH,
        description="The key of the category, whole.",
    )
    source: AliasSource | None = Field(
        None, description="shipped (factory) or learned."
    )
    sort: Literal["alias", "tax_category_key", "source", "is_active", "id"] = Field(
        "alias", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=DIRECTION)


class AliasResolveIn(Schema):
    text: AliasText = Field(
        description="An outside text (a CSV cell: IVA 10, beer, comida) to read as a category."
    )


class AliasIn(Schema):
    alias: AliasText = Field(
        description="The outside text; kept lowercase with single spaces."
    )
    tax_category_key: CategoryRef = Field(title=CATEGORY, description=CATEGORY_REF, json_schema_extra=A_TAX_CATEGORY)
    source: AliasSource = Field(
        "learned", description="learned (the default) or shipped (factory)."
    )


class AliasOut(Schema):
    id: UUID = Field(description="The alias's id.")
    alias: str = Field(description="The outside text.")
    tax_category_key: str = Field(description="The key of its category.")
    tax_category_name: str = Field(
        description="The name of its category, in the reader's language."
    )
    source: AliasSource = Field(description="shipped (factory) or learned.")
    is_active: bool = Field(description="Active.")


AliasPage = Page[AliasOut]


class AliasResolveOut(Schema):
    text: str = Field(description="The text as compared (lowercase, single spaces).")
    tax_category_key: str | None = Field(
        description="The key of the category it is; empty if none."
    )
    matched_by: Literal["key", "name", "alias"] | None = Field(
        description="What matched: key, name or alias."
    )
