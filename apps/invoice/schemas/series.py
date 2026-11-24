"""Schemas of the numbering series: the list, one series, creating and changing one, and its next number.
"""

import re
from typing import Annotated, Any, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import AfterValidator, BeforeValidator, StringConstraints, field_validator, model_validator

from apps.invoice import fiscal
from apps.invoice.models import SERIES_CODE_MAX_LENGTH, SERIES_CODE_RE
from apps.invoice.schemas.fields import (
    A_SERIES,
    DIRECTION,
    NEXT_NUMBER,
    SEARCH,
    Direction,
    InvoiceTypeCode,
    Page,
    PageIn,
    _blank_to_none,
    _text,
)

FORMAT_INVALID = _(
    "The format needs the year ({year}) and a sequence placeholder ({seq} or {seq:01d}…{seq:09d}), and fits in "
    "one line of 60 characters without accents or symbols such as º or ª."
)
SERIES_CODE_INVALID = _(
    "Use only letters without accents, digits, hyphens (-) and underscores (_), starting with a letter or a digit."
)
PREFIX_INVALID = _(
    "The prefix is written without accents or symbols such as º or ª (letters, digits, spaces and - / . _)."
)
WHICH_SERIES = _("Say which series: its id, or its code.")


def _upper_code(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _series_code(value: str) -> str:
    # Its own message, as the format's: pydantic's pattern would say only «Enter a valid value.»
    if not re.fullmatch(SERIES_CODE_RE, value):
        raise ValueError(str(SERIES_CODE_INVALID))
    return value


SeriesCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=SERIES_CODE_MAX_LENGTH),
    BeforeValidator(_upper_code),
    AfterValidator(_series_code),
    # The shape stays in the OpenAPI and in the assistant's tool, as when the pattern checked it.
    Field(json_schema_extra={"pattern": SERIES_CODE_RE}),
]


def _format(value: str) -> str:
    text = value.strip()
    if text and not fiscal.format_is_valid(text):
        raise ValueError(str(FORMAT_INVALID))
    return text


def _prefix(value: str | None) -> str | None:
    # NumSerieFactura admits printable ASCII only (and no tab: one line).
    if value is not None and not fiscal.is_printable_ascii(value):
        raise ValueError(str(PREFIX_INVALID))
    return value


class SeriesListIn(PageIn):
    """The numbering series."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Code or name."
    )
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this code."
    )
    invoice_type: InvoiceTypeCode | None = Field(None, description="Only this type.")
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")
    is_active: bool | None = Field(
        None, description="True: active ones only; false: inactive ones only."
    )
    is_default: bool | None = Field(None, description="True: the default ones only.")
    sort: Literal[
        "code",
        "name",
        "invoice_type",
        "year",
        "current_number",
        "prefix",
        "is_active",
        "is_default",
    ] = Field("year", description="Column to sort by.")
    dir: Direction = Field("desc", description=DIRECTION)


class SeriesCreateIn(Schema):
    code: SeriesCode = Field(
        description="Code of the series: capitals, digits, hyphen, underscore (TICKET, FACT, RECT…)."
    )
    name: _text(120) = Field("", description="Name of the series.")
    invoice_type: InvoiceTypeCode = Field(
        description="Type of the documents it numbers: F1, F2, F3 or R1–R5."
    )
    year: int = Field(ge=2000, le=2999, description="Year it numbers.")
    prefix: _text(20) = Field(
        "", description="Text before the number; empty = the code."
    )
    format: str = Field(
        "",
        max_length=fiscal.FORMAT_MAX_LENGTH,
        description="Number template with {prefix}, {code}, {year}, {seq} or {seq:01d}…{seq:09d}; empty = "
        "PREFIX-YYYY-NNNNNN.",
    )
    next_number: int = Field(
        1,
        ge=1,
        title=NEXT_NUMBER,
        description="The number its first document takes (to continue another system).",
    )
    is_active: bool = Field(True, description="Offered when issuing by hand.")
    is_default: bool = Field(
        False, description="The series a manual invoice proposes; one per year."
    )

    @field_validator("format")
    @classmethod
    def _valid_format(cls, value: str) -> str:
        return _format(value)

    @field_validator("prefix")
    @classmethod
    def _valid_prefix(cls, value: str) -> str:
        return _prefix(value)


class SeriesUpdateIn(Schema):
    series_id: UUID = Field(description="Id of the series.", json_schema_extra=A_SERIES)
    name: _text(120) | None = Field(None, description="New name.")
    prefix: _text(20) | None = Field(
        None, description="New prefix (only while the series has numbered nothing)."
    )
    format: str | None = Field(
        None,
        max_length=fiscal.FORMAT_MAX_LENGTH,
        description="New number template (only while the series has numbered nothing); empty = PREFIX-YYYY-NNNNNN.",
    )
    next_number: int | None = Field(
        None,
        ge=1,
        title=NEXT_NUMBER,
        description="New first number (only while the series has numbered nothing).",
    )
    is_active: bool | None = Field(None, description="Offered when issuing by hand.")
    is_default: bool | None = Field(None, description="The default series of its year.")

    @field_validator("format")
    @classmethod
    def _valid_format(cls, value: str | None) -> str | None:
        return None if value is None else _format(value)

    @field_validator("prefix")
    @classmethod
    def _valid_prefix(cls, value: str | None) -> str | None:
        return _prefix(value)


class SeriesPeekIn(Schema):
    series_id: UUID | None = Field(None, description="Id of the series.")
    code: Annotated[
        _text(SERIES_CODE_MAX_LENGTH) | None, BeforeValidator(_blank_to_none)
    ] = Field(None, description="Code of the series instead of its id.")
    year: int | None = Field(
        None,
        ge=2000,
        le=2999,
        description="Year of the series named by code; default this year.",
    )

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.series_id is None and not self.code:
            raise ValueError(str(WHICH_SERIES))
        return self


class SeriesOut(Schema):
    id: UUID
    code: str
    name: str
    display_name: str
    invoice_type: str
    year: int
    prefix: str
    format: str
    current_number: int
    next_number: str = Field(description="The number its next document will carry.")
    format_locked: bool
    is_active: bool
    is_default: bool


class SeriesDetailOut(SeriesOut):
    """One series as the Series screen shows it, and how it is named outside its screen."""

    label: str = Field(
        description="How it is named outside its screen, in the reader's language: its code, its year and its name "
        "(e.g. «FACT · 2026 · Invoices»)."
    )


class SeriesPeekOut(Schema):
    series_id: UUID
    code: str
    year: int
    next_sequence: int
    next_number: str
    format_locked: bool


SeriesPage = Page[SeriesOut]
