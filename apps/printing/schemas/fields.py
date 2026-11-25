"""What the schemas of the printing app share: the types and limits of their fields, the titles and record marks
the assistant's card reads, pages and the closed input."""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import BeforeValidator, ConfigDict, StringConstraints

from base.schemas.assistant import names

T = TypeVar("T")

#: Printers one device asks for at once: more than any business has next to one till.
MAX_CLAIM_PRINTERS = 20

# How the Printing screens name the data the models do not (the assistant's card names each datum by its title).
JOB = gettext_noop("Job")
ATTEMPT = gettext_noop("Attempt")
REFERENCE = gettext_noop("Reference")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a printer and a device by their names, as the Printers and Devices screens; a job as the queue
# titles it («Receipt T-000123»). Whoever prints or sets up the printers reads them all.
A_PRINTER = names("printing.printer.get", by="printer_id")
A_DEVICE = names("printing.device.detail", by="device_id")
A_JOB = names("printing.job.get", by="job_id", name=("label",))
#: A printer of a list of them, by its id (a device's printers).
PrinterId = Annotated[UUID, Field(json_schema_extra=A_PRINTER)]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


def _cut(max_length: int):
    """Trim and cut a text that comes from a device (an error), instead of refusing it for its length."""

    def cut(value: Any) -> Any:
        return value.strip()[:max_length] if isinstance(value, str) else value

    return BeforeValidator(cut)


Name = _text(100, 1)
Reason = _text(500)
JobKey = _text(128, 1)
DeviceName = _text(128, 1)
DeviceError = Annotated[str, _cut(500), StringConstraints(min_length=1, max_length=500)]
Usage = Literal["receipt", "kitchen", "bar", "label"]
PrinterKind = Literal["network", "usb", "bluetooth", "system"]
PaperWidth = Literal[80, 58]
JobKind = Literal["document", "test_page", "drawer"]
JobFormat = Literal["receipt", "a4"]
JobStatus = Literal["pending", "sent", "done", "failed", "cancelled"]
PrinterState = Literal["ready", "waiting", "failing", "inactive"]
DocumentType = Literal[
    "receipt",
    "kitchen_order",
    "invoice",
    "delivery_note",
    "barcode_label",
    "cash_session_report",
    "prebill",
    "generic",
]
SortDir = Literal["asc", "desc"]


class Closed(Schema):
    """An input that refuses fields it does not know (a typo is a 422, never silently ignored)."""

    model_config = ConfigDict(extra="forbid")


class EmptyIn(Closed):
    pass


class PageIn(Closed):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")
