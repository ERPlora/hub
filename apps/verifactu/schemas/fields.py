"""The types, codes, limits, pages and record and issuer names the schemas of VeriFactu share."""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import BeforeValidator, StringConstraints, model_validator

from apps.verifactu import card_names
from apps.verifactu.models import Config, Event, Record


T = TypeVar("T")

WHICH_RECORD = _("Say which record: its id or the number of its invoice.")
RECORD_ID = "Id of the record."
INVOICE_NUMBER = "Number of the invoice (e.g. TICKET-2026-000012): its latest record."
ISSUER_NIF = "Tax ID of the issuer (Invoicing's issuer when left out)."
SEARCH = "Words to look for."

Direction = Literal["asc", "desc"]
StatusCode = Literal[*Record.Status.values]
TypeCode = Literal[*Record.Type.values]
EnvironmentCode = Literal[*Config.Environment.values]
RouteCode = Literal[*Config.Route.values]
InvoiceTypeCode = Literal["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"]
KindCode = Literal[*Event.Kind.values]
SeverityCode = Literal[*Event.Severity.values]
RepresentationCode = Literal[*Config.Representation.values]
# Where a registration the AEAT rejected or accepted with errors stands (VERIFACTU-F24): not corrected yet, or
# corrected by a newer record; any other record has nothing to correct.
CorrectionStatusCode = Literal["not_applicable", "pending", "corrected"]


def _text(max_length: int, *, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


OptionalText = lambda length: Annotated[
    _text(length) | None, BeforeValidator(_blank_to_none)
]  # noqa: E731


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


class NoInput(Schema):
    """No parameters."""


class RecordRefIn(Schema):
    """A record, by its id or by the number of its invoice (its latest record)."""

    record_id: UUID | None = Field(None, description=RECORD_ID, json_schema_extra=card_names.A_RECORD)
    invoice_number: OptionalText(60) = Field(None, description=INVOICE_NUMBER)

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.record_id is None and not self.invoice_number:
            raise ValueError(str(WHICH_RECORD))
        return self


class IssuerIn(Schema):
    issuer_nif: OptionalText(32) = Field(None, description=ISSUER_NIF)


class WaitOut(Schema):
    code: str = Field(description="Why it waits, as a code.")
    message: str = Field(description="Why it waits, in the reader's language.")
