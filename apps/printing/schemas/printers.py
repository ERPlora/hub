"""Schemas of the printers (``printing.printer.*``)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.printing.schemas.fields import (
    A_PRINTER,
    Closed,
    Name,
    PageIn,
    PaperWidth,
    PrinterKind,
    PrinterState,
    SortDir,
    Usage,
    _text,
)

SAY_WHICH_PRINTER = _("Say which printer: its id or its name.")
NOTHING_TO_CHANGE = _("Say what changes in the printer.")


class PrinterIn(Closed):
    name: Name = Field(description="The printer's name, e.g. Till or Kitchen.")
    kind: PrinterKind = Field(
        description="How it is connected: network (IP), usb (the computer's print queue), bluetooth (paired) or "
        "system (the computer's own A4 printer)."
    )
    address: _text(255) = Field(
        "",
        description="network: its IP or network name (192.168.1.100); bluetooth: its MAC (AA:BB:CC:DD:EE:FF); usb: "
        "the name of its print queue; system: empty.",
    )
    port: int | None = Field(None, description="network only: its port, 9100 when not given.")
    paper_width: PaperWidth = Field(
        80,
        description="Its paper: 80 or 58 mm, kept with the printer; the ERPlora app prints 32 characters a line for "
        "now, whatever the paper (ignored by the system printer).",
    )
    usage: Usage = Field(
        description="What it prints: receipt (receipts, invoices, bills, cash reports), kitchen, bar or label."
    )
    is_active: bool = Field(True, description="It takes jobs.")


class PrinterRefIn(Closed):
    printer_id: UUID | None = Field(None, description="The printer's id.", json_schema_extra=A_PRINTER)
    printer: Name | None = Field(None, description="Its name, when the id is not known («Kitchen»).")

    @model_validator(mode="after")
    def _named(self):
        if self.printer_id is None and self.printer is None:
            raise ValueError(str(SAY_WHICH_PRINTER))
        return self


class PrinterUpdateIn(PrinterRefIn):
    name: Name | None = Field(None, description="Its new name.")
    kind: PrinterKind | None = Field(None, description="Its new connection.")
    address: _text(255) | None = Field(None, description="Its new address (see printing.printer.create).")
    port: int | None = Field(None, description="Its new port (network only).")
    paper_width: PaperWidth | None = Field(None, description="Its new paper: 80 or 58 mm.")
    usage: Usage | None = Field(None, description="Its new function.")
    is_active: bool | None = Field(None, description="Activate (true) or deactivate (false) it.")

    @model_validator(mode="after")
    def _changes(self):
        changes = ("name", "kind", "address", "port", "paper_width", "usage", "is_active")
        if all(getattr(self, field) is None for field in changes):
            raise ValueError(str(NOTHING_TO_CHANGE))
        return self


class PrinterListIn(PageIn):
    search: str | None = Field(None, max_length=100, description="Part of the printer's name or address.")
    usage: Usage | None = Field(None, description="Only the printers of this function.")
    kind: PrinterKind | None = Field(None, description="Only the printers of this connection.")
    is_active: bool | None = Field(None, description="Only active (or inactive) printers.")
    sort: Literal["name", "usage", "kind", "created_at"] = Field("name", description="Order by.")
    dir: SortDir = Field("asc", description="Ascending or descending.")


class PrinterOut(Schema):
    id: UUID = Field(description="The printer's id.")
    name: str = Field(description="Its name.")
    kind: PrinterKind = Field(description="Its connection.")
    address: str = Field(description="Its address (empty for the system printer).")
    port: int | None = Field(description="Its port (network only).")
    paper_width: int = Field(description="Its paper, 80 or 58 mm.")
    usage: Usage = Field(description="What it prints.")
    is_active: bool = Field(description="It takes jobs.")
    target: str = Field(
        description="The printer id the ERPlora app's print commands take: network:<ip>:<port>, bluetooth:<mac>, "
        "usb:<queue> or system."
    )
    oldest_pending_at: datetime | None = Field(description="When its oldest waiting job was queued.")
    state: PrinterState = Field(
        description="ready; waiting (a job queued for over a minute); failing (its last attempt failed); inactive."
    )
    pending: int = Field(description="Its jobs waiting in the queue.")
    last_printed_at: datetime | None = Field(description="When it last printed.")
    last_failed_at: datetime | None = Field(description="When it last failed.")
    last_error: str = Field(description="Its last error, as the device said it.")
    created_at: datetime = Field(description="When it was added.")


class PrinterStatusOut(Schema):
    printer: PrinterOut = Field(description="The printer, with its state.")
    is_default: bool = Field(description="It is the printer of its function in the settings.")
    pending: int = Field(description="Its jobs waiting in the queue.")
    oldest_pending_at: datetime | None = Field(description="When the oldest of them was queued.")
    sent: int = Field(description="Its jobs sent to a device and not confirmed yet.")
    failed: int = Field(description="Its failed jobs, waiting to be retried or cancelled.")
