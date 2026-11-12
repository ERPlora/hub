"""Input and output schemas of the demo app's operations (OpenAPI, live params, 422 per field)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from base.schemas import names, unless_given

T = TypeVar("T")

Status = Literal["open", "done"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LineText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# What the assistant's card calls the item a write acts on (its Spanish in this app's catalog), as its screen calls one,
# and the read it names that item by (base/assistant.py ``REFERS``), run as whoever asks, never by its id: by its name,
# as the list and the «Delete» dialog say it. Said by its name, the card reads it by that name too, so it shows the item
# the write will find («Autumn trial» when the person said «autumn»), not only what was said; beside the item's id,
# which the write takes it by instead, the card neither reads nor shows the name (``unless_given``, hub#1272).
T_ITEM = gettext_noop("Item")
AN_ITEM = names("demo.item.detail")
AN_ITEM_BY_NAME = names("demo.item.detail", by="called")
NO_ITEM = _("Say which item: its id or its name.")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int
    limit: int
    offset: int


# Inputs


class ItemListIn(PageIn):
    search: str | None = Field(None, max_length=120)
    status: Status | None = None


class ItemRefIn(Schema):
    """An item by its ``id`` or, when the id is not known, by its name as a person says it (``called``; the same name
    in any case before one that contains it: ``queries.find_item``). The id wins.

    The name travels as ``called``, not as ``item``: a turn ranks a tool 1 higher for each datum it takes that the
    question names (``live.assistant.relevant``), and «item» (and «elemento», ``base.assistant.SYNONYMS``) is what the
    cart's and the price lists' items are called too (``cart_checkout``, ``pricing``), so an ``item`` datum would lift
    Demo's four tools in their requests (measured on hub#1162: three asks of ``inventory.product.bulk_create`` went
    from 4th to 8th); ``called`` moves no ask nor probe of the Hub."""

    id: UUID | None = Field(None, title=T_ITEM, json_schema_extra=AN_ITEM)
    called: Name | None = Field(
        None,
        validate_default=True,
        title=T_ITEM,
        description="The item's name, when its id is not known.",
        json_schema_extra=unless_given(AN_ITEM_BY_NAME, "id"),
    )

    @field_validator("called")
    @classmethod
    def _said(cls, value: str | None, info: ValidationInfo) -> str | None:
        """The name is required when the id is not given (and the id itself is valid: a malformed one is its own
        error)."""
        if value is None and "id" in info.data and info.data["id"] is None:
            raise ValueError(str(NO_ITEM))
        return value


class ItemStatsIn(Schema):
    pass


class ItemIn(Schema):
    name: Name
    status: Status = "open"
    note: str = ""


class ItemPatchIn(ItemRefIn):
    """The item by its id or its name; only the fields sent are changed, ``null`` leaves a field as it is."""

    name: Name | None = None
    status: Status | None = None
    note: str | None = None


class LineIn(ItemRefIn):
    """The item by its id or its name; ``client_line_id`` makes repeating the same line safe."""

    text: LineText
    qty: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    client_line_id: UUID | None = Field(None, json_schema_extra={"attempt_key": True})


# Outputs


class ItemOut(Schema):
    id: UUID
    name: str
    status: Status
    note: str
    line_count: int
    updated_at: datetime


class LineOut(Schema):
    id: UUID
    text: str
    qty: Decimal
    position: int
    client_line_id: UUID | None


class ItemDetailOut(ItemOut):
    lines: list[LineOut]


ItemPage = Page[ItemOut]


class ItemStatsOut(Schema):
    total: int
    open: int
    done: int
    lines: int


class ItemCountOut(Schema):
    """How many items there are of a kind: the bell's example counter (its first row brings ``count``)."""

    count: int


class DeletedOut(Schema):
    id: UUID
