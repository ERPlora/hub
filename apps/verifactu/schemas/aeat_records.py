"""What the AEAT holds: the records it gave back when asked, and the question put to it."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.verifactu.schemas.fields import SEARCH, Direction, EnvironmentCode, IssuerIn, OptionalText, PageIn


class AeatRecordOut(Schema):
    id: UUID = Field(description="Id of the row.")
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="testing or production.")
    invoice_number: str = Field(description="Invoice number.")
    issue_date: dt.date | None = Field(description="Issue date.")
    fingerprint: str = Field(description="Fingerprint the AEAT holds.")
    state: str = Field(description="The AEAT's state of it.")
    csv: str = Field(description="CSV, if the AEAT gave it.")
    generated_on: dt.datetime | None = Field(description="When it was generated.")
    queried_at: dt.datetime = Field(description="When the AEAT was asked.")


class AeatQueryOut(Schema):
    count: int = Field(description="Records the AEAT returned.")
    rows: list[AeatRecordOut] = Field(description="Those records.")


#: How the AEAT's query names the state of a record it holds (``EstadoRegistro`` of RespuestaConsultaLR.xsd).
AeatStateCode = Literal["Correcto", "AceptadoConErrores", "Anulado"]


class AeatRecordListIn(PageIn):
    """The last photo of the AEAT, the last generated first unless sorted otherwise."""

    search: OptionalText(120) = Field(
        None, description=SEARCH + " Invoice number, fingerprint or CSV."
    )
    state: AeatStateCode | None = Field(None, description="Only this state at the AEAT.")
    issue_date_from: dt.date | None = Field(
        None, description="Invoices issued on this day or later."
    )
    issue_date_to: dt.date | None = Field(
        None, description="Invoices issued on this day or earlier."
    )
    sort: Literal["generated_on", "invoice_number", "issue_date", "fingerprint", "state", "csv", "queried_at"] | None = Field(
        None, description="Column to sort by (the last generated first by default)."
    )
    dir: Direction = Field("desc", description="asc or desc.")


class AeatQueryIn(IssuerIn):
    year: int | None = Field(
        None,
        ge=2024,
        le=2999,
        title=gettext_noop("Year"),
        description="Year (this one by default).",
    )
    month: int | None = Field(
        None,
        ge=1,
        le=12,
        title=gettext_noop("Month"),
        description="Month, 1 to 12 (this one by default).",
    )
