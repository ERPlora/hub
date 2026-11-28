"""What the schemas of the online booking app share: a booking's status, the text fields, the closed input and the
page of a list."""

from typing import Annotated, Generic, Literal, TypeVar

from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

T = TypeVar("T")

Status = Literal[
    "pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class NoIn(In):
    pass


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")
