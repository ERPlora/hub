"""What every schema of the inventory app shares: field types, limits, titles, pages and references."""

from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, model_validator

from base.schemas import assistant

T = TypeVar("T")

#: Ninety-nine billion euros in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Rows of one bulk create (CSV import) or lines of one reception.
MAX_BATCH = 100

SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")
SAY_WHICH_CATEGORY = _("Say which category: its id, or its name.")

# How the Inventory screens name the data the models do not (the assistant's card names each datum by its title).
TAX_CATEGORY = gettext_noop("Tax category")
CATEGORIES = gettext_noop("Categories")
FILE_ROWS = gettext_noop("File rows")
#: The category form's own name for its tax category.
TAX_RATE = gettext_noop("Tax rate")
# What the assistant's card calls the record a write acts on by its id (its Spanish in this app's catalog), as the
# screens call one («Delete product», «New category»), never «Record».
T_PRODUCT = gettext_noop("Product")
T_CATEGORY = gettext_noop("Category")

UnitCode = Literal["ud", "kg", "g", "t", "l", "ml", "min", "h"]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


TaxKey = _text(64, 1)
Description = Annotated[str, StringConstraints(max_length=2000)]
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, json_schema_extra={"money": True})]
Quantity = Annotated[Decimal, Field(max_digits=15, decimal_places=3)]
#: How a person names a product (its SKU or name) or a category (its name or slug).
Said = _text(200, 1)
#: A product has one name, in the language it was written in: the model looks it up with what the person said.
IN_THEIR_WORDS = "in the person's own words, never translated"
PRODUCT_SAID = (
    f"The product's SKU or name, when its id is not known (e.g. said aloud), {IN_THEIR_WORDS}: a product has one "
    "name, in the language it was written in; if none matches, ask."
)
ProductSearch = Annotated[
    str | None, Field(max_length=200, description=f"Part of the name or the SKU, {IN_THEIR_WORDS}.")
]

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a product and a category by their name, as the screens' «Delete» dialogs and forms say them.
A_PRODUCT = assistant.names("inventory.product.get")
A_CATEGORY = assistant.names("inventory.category.get")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


# References: by id, or as a person says it


class ProductRefIn(Schema):
    id: UUID | None = Field(None, title=T_PRODUCT, description="The product's id.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(None, description=PRODUCT_SAID)

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class CategoryRefIn(Schema):
    id: UUID | None = Field(None, title=T_CATEGORY, description="The category's id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None, description="The category's name or slug, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


class _ProductLineRef(Schema):
    """A product named by ``product_id`` or by its SKU or name (``product``)."""

    product_id: UUID | None = Field(None, description="The product's id.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(None, description=PRODUCT_SAID)

    @model_validator(mode="after")
    def _named(self):
        if self.product_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class DeletedOut(Schema):
    id: UUID = Field(description="What was deleted.")
