"""Input and output schemas of the demo app's operations (OpenAPI, live params, 422 per field)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from ninja import Field, Schema
from pydantic import StringConstraints

T = TypeVar("T")

Status = Literal["open", "done"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LineText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


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


class ByIdIn(Schema):
    id: UUID


class ItemStatsIn(Schema):
    pass


class ItemIn(Schema):
    name: Name
    status: Status = "open"
    note: str = ""


class ItemPatchIn(Schema):
    """Only the fields sent are changed; ``null`` leaves a field as it is."""

    id: UUID
    name: Name | None = None
    status: Status | None = None
    note: str | None = None


class LineIn(Schema):
    """``id`` is the item's; ``client_line_id`` makes repeating the same line safe."""

    id: UUID
    text: LineText
    qty: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    client_line_id: UUID | None = None


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


class DeletedOut(Schema):
    id: UUID
