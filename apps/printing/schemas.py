"""Input and output schemas of the printing app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. What a person names
aloud is accepted besides the id: a printer by its name («the kitchen one»), a job by the number of its
document («T-000123»). The document of a job travels structured, in the shape the app's renderer reads
(WORKBOOK «Contrato con la plataforma»); only an A4 job carries a page.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import BeforeValidator, ConfigDict, JsonValue, StringConstraints, model_validator

T = TypeVar("T")

#: An A4 page is a document with its styles and its QR inline, not a file upload.
MAX_HTML_BYTES = 2 * 1024 * 1024
#: Printers one device asks for at once: more than any business has next to one till.
MAX_CLAIM_PRINTERS = 20

SAY_WHICH_PRINTER = _("Say which printer: its id or its name.")
SAY_WHICH_JOB = _("Say which job: its id or the number of its document.")
NOTHING_TO_CHANGE = _("Say what changes in the printer.")
NOTHING_TO_CHANGE_DEVICE = _("Say what changes in the device: its name or its printers.")
A4_NEEDS_PAGE = _("An A4 job carries its A4 page (html).")
PAGE_ONLY_A4 = _("Only an A4 job carries a page: a receipt printer prints the structured document.")
PAGE_TOO_LARGE = _("The A4 page is larger than 2 MB.")
PAGE_WITH_SCRIPT = _("The A4 page cannot carry a script.")
A4_ONCE = _("An A4 page prints once: ask for another job for another copy.")

_SCRIPT = re.compile(r"<\s*script\b", re.IGNORECASE)


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


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


class SettingsOut(Schema):
    print_receipt_on_sale: bool = Field(description="The receipt prints by itself when a sale is charged.")
    open_drawer_on_sale: bool = Field(description="The drawer opens with the receipt when a sale is charged.")
    receipt_copies: int = Field(description="Copies of each receipt, 1 to 3.")
    receipt_printer_id: UUID | None = Field(description="The printer of the receipts; none = the first active one.")
    kitchen_printer_id: UUID | None = Field(description="The printer of the kitchen; none = the first active one.")
    bar_printer_id: UUID | None = Field(description="The printer of the bar; none = the first active one.")
    label_printer_id: UUID | None = Field(description="The printer of the labels; none = the first active one.")
    updated_at: datetime | None = Field(description="When they were last saved; none = the factory values.")


class SettingsPatchIn(Closed):
    print_receipt_on_sale: bool | None = Field(None, description="Print the receipt by itself at checkout.")
    open_drawer_on_sale: bool | None = Field(None, description="Open the drawer with the receipt at checkout.")
    receipt_copies: int | None = Field(None, ge=1, le=3, description="Copies of each receipt, 1 to 3.")
    receipt_printer: str | None = Field(
        None, max_length=100, description="The receipts' printer by its id or name; null = the first active one."
    )
    kitchen_printer: str | None = Field(
        None, max_length=100, description="The kitchen's printer by its id or name; null = the first active one."
    )
    bar_printer: str | None = Field(
        None, max_length=100, description="The bar's printer by its id or name; null = the first active one."
    )
    label_printer: str | None = Field(
        None, max_length=100, description="The labels' printer by its id or name; null = the first active one."
    )


# ── Printers ──────────────────────────────────────────────────────────────────────────────────────


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
    printer_id: UUID | None = Field(None, description="The printer's id.")
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


# ── Jobs ──────────────────────────────────────────────────────────────────────────────────────────


class JobCreateIn(Closed):
    job_key: JobKey | None = Field(
        None,
        description="Idempotency key of the caller (sale-<id>-receipt): two requests with the same key are one job. "
        "Without it, a new one.",
    )
    document_type: DocumentType = Field(description="Which document it is: the eight the printer knows how to paint.")
    document: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The structured document (never HTML for a receipt printer), with the fields the printer reads: "
        "a receipt has business_name, receipt_id, items [{name, quantity, total}], subtotal, tax_amount, total, "
        "payment_method, qr_data…; a barcode_label has product_name, barcode and price. Amounts in units (12.50).",
    )
    format: JobFormat = Field("receipt", description="receipt (a thermal printer) or a4 (the computer's printer).")
    html: str | None = Field(None, description="The whole A4 page, for an a4 job only (no scripts, at most 2 MB).")
    usage: Usage | None = Field(
        None, description="The function that prints it; without it, from the document: kitchen_order → kitchen, "
        "barcode_label → label, the rest → receipt."
    )
    printer: Name | None = Field(None, description="A given printer, by its id or its name («Kitchen»).")
    copies: int | None = Field(
        None,
        ge=1,
        le=5,
        description="Copies, 1 to 5; without it, the settings' receipt copies for a receipt, else 1. Every copy after "
        "the first of a receipt or an invoice prints as a duplicate.",
    )
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = Field(
        None,
        description="The amounts' currency (ISO 4217), for their decimals; without it, the business's.",
    )
    automatic: bool = Field(
        False,
        description="The print by itself at checkout: it follows «print the receipt at checkout» and «open the drawer "
        "at checkout» of the settings.",
    )
    open_drawer: bool = Field(
        True,
        description="With automatic: false keeps the drawer shut whatever the settings (a checkout with no cash).",
    )
    source_app: _text(32) | None = Field(None, description="The app that asks for it (sale).")
    source_ref: _text(64) | None = Field(None, description="The document it is, as a person reads it (T-000123).")

    @model_validator(mode="after")
    def _page(self):
        if self.format == "a4":
            if not self.html or not self.html.strip():
                raise ValueError(str(A4_NEEDS_PAGE))
            if len(self.html.encode()) > MAX_HTML_BYTES:
                raise ValueError(str(PAGE_TOO_LARGE))
            if _SCRIPT.search(self.html):
                raise ValueError(str(PAGE_WITH_SCRIPT))
            if self.copies is not None and self.copies > 1:
                raise ValueError(str(A4_ONCE))
        elif self.html is not None:
            raise ValueError(str(PAGE_ONLY_A4))
        return self


class JobOut(Schema):
    id: UUID = Field(description="The job's id.")
    job_key: str = Field(description="Its idempotency key.")
    kind: JobKind = Field(description="document, test_page or drawer (open the drawer only).")
    document_type: str = Field(description="The document (empty for a test page or the drawer).")
    reference: str = Field(description="What names it: the number of its document (T-000123) or its title.")
    format: JobFormat = Field(description="receipt or a4.")
    usage: Usage = Field(description="The function that prints it.")
    printer_id: UUID | None = Field(description="Its printer; none = the first device with a printer of its function.")
    printer_name: str | None = Field(description="Its printer's name.")
    copies: int = Field(description="Copies.")
    open_drawer: bool = Field(description="The drawer opens after it prints.")
    status: JobStatus = Field(
        description="pending (queued), sent (a device has it), done (printed), failed (gave up after 5 hand-outs) or "
        "cancelled."
    )
    attempts: int = Field(description="Times a device took it.")
    leased_until: datetime | None = Field(description="Sent: the device must answer before this moment.")
    stale: bool = Field(description="Sent and with no answer past its 90 s.")
    retryable: bool = Field(description="It can be sent back to the queue (queued, failed, or sent with no answer).")
    cancellable: bool = Field(description="It can be cancelled (queued, failed, or sent with no answer).")
    device: str = Field(description="The name of the device that took it last (never its own id).")
    last_error: str = Field(description="Its last error, as the device said it.")
    source_app: str = Field(description="The app that asked for it.")
    created_at: datetime = Field(description="When it was asked for.")
    created_by: str = Field(description="Who asked for it.")
    sent_at: datetime | None = Field(description="When a device took it last.")
    printed_at: datetime | None = Field(description="When it printed.")
    failed_at: datetime | None = Field(description="When it last failed.")
    retried_at: datetime | None = Field(description="When it was last sent back to the queue.")
    retried_by: str = Field(description="Who sent it back.")
    cancelled_at: datetime | None = Field(description="When it was cancelled.")
    cancelled_by: str = Field(description="Who cancelled it.")
    cancel_reason: str = Field(description="Why.")


class JobCreateOut(Schema):
    job: JobOut | None = Field(description="The job queued (or the one already queued with that key); none = nothing.")
    duplicate: bool = Field(description="A job with that key was already in the queue: nothing new was queued.")
    skipped: Literal["print_on_sale_off"] | None = Field(
        description="Why the receipt was not queued: the business does not print it at checkout."
    )


class JobListIn(PageIn):
    search: str | None = Field(None, max_length=64, description="Part of the document's number or title.")
    status: JobStatus | None = Field(None, description="Only the jobs in this state.")
    usage: Usage | None = Field(None, description="Only the jobs of this function.")
    printer_id: UUID | None = Field(None, description="Only the jobs of this printer.")
    sort: Literal["created_at", "status", "usage", "attempts"] = Field("created_at", description="Order by.")
    dir: SortDir = Field("desc", description="Ascending or descending.")


class JobRefIn(Closed):
    job_id: UUID | None = Field(None, description="The job's id.")
    reference: _text(64, 1) | None = Field(
        None, description="The number of its document (T-000123), when the id is not known: its newest job."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.job_id is None and self.reference is None:
            raise ValueError(str(SAY_WHICH_JOB))
        return self


class JobCancelIn(JobRefIn):
    reason: Reason = Field("", description="Why it is cancelled (optional).")


class UsageSummary(Schema):
    usage: Usage = Field(description="The function.")
    printers: int = Field(description="Its active printers.")
    default_printer: str | None = Field(description="The printer chosen for it in the settings, if any.")
    prints_on: str | None = Field(
        description="The printer its next job goes to now: the chosen one if active, else its first active roll-paper "
        "printer by name, else its computer's printer; none when no active printer has the function."
    )
    pending: int = Field(description="Its jobs waiting.")
    oldest_pending_at: datetime | None = Field(description="When the oldest of them was queued.")
    sent: int = Field(description="Its jobs a device has and has not confirmed.")
    failed: int = Field(description="Its failed jobs.")


class JobSummaryOut(Schema):
    usages: list[UsageSummary] = Field(description="Each function, receipts, kitchen, bar and labels, in that order.")
    pending: int = Field(description="Jobs waiting, every function.")
    sent: int = Field(description="Jobs a device has and has not confirmed, every function.")
    failed: int = Field(description="Failed jobs, every function.")


# ── The device that prints (base's /ws/print) ─────────────────────────────────────────────────────


class JobClaimIn(Closed):
    printers: list[UUID] = Field(
        min_length=1,
        max_length=MAX_CLAIM_PRINTERS,
        description="The printers this device reaches (their ids): the ones it was set up with.",
    )
    device: DeviceName = Field(
        description="The device's own id (its deviceId): what proves it is the device set up to print here."
    )


class HostJobOut(Schema):
    id: UUID = Field(description="The job's id: what the device confirms.")
    kind: JobKind = Field(
        description="document → erplora_print (or print_document for a4); test_page → erplora_test_print; drawer → "
        "erplora_open_drawer."
    )
    printer_id: UUID = Field(description="The printer it goes to.")
    target: str = Field(description="The printer id the app's commands take (network:<ip>:<port>…).")
    paper_width: int = Field(description="The printer's paper, 80 or 58 mm.")
    document_type: str = Field(description="The document type the app's renderer paints.")
    document: dict[str, Any] = Field(description="The structured document (the renderer's data): the first copy.")
    copy_document: dict[str, Any] | None = Field(
        description="What every copy after the first prints: a receipt or an invoice marked duplicate (it is no second "
        "original), any other document as it is; none with one copy."
    )
    format: JobFormat = Field(description="receipt or a4.")
    html: str = Field(description="The A4 page (a4 only).")
    copies: int = Field(description="Times to print it.")
    open_drawer: bool = Field(description="Open the drawer after printing.")
    attempts: int = Field(description="Times it has been handed out, this one included.")
    leased_until: datetime = Field(
        description="When the device's time to answer runs out: past it, the job goes back to the queue."
    )


class JobClaimOut(Schema):
    job: HostJobOut | None = Field(description="The next job for this device; none = nothing waiting (idle).")


class JobCompleteIn(Closed):
    job_id: UUID = Field(description="The job the device printed.")
    device: DeviceName = Field(description="The own id of the device that printed it: the one that took it.")
    attempt: int = Field(ge=1, description="The hand-out it printed (the `attempts` it was given).")


class JobFailIn(Closed):
    job_id: UUID = Field(description="The job the device could not print.")
    device: DeviceName = Field(description="The own id of the device that could not print it: the one that has it.")
    attempt: int = Field(ge=1, description="The hand-out that failed (the `attempts` it was given).")
    error: DeviceError = Field(description="Why, as the device says it (cut at 500 characters).")


class JobAckOut(Schema):
    confirmed: bool = Field(
        description="The answer was taken; false = the job was no longer the device's (it went back to the queue, "
        "was retried or cancelled)."
    )
    job: JobOut = Field(description="The job as it is now.")


# ── The devices that print (PRINTING-F18) ────────────────────────────────────────────────────────


class DevicePrinterOut(Schema):
    id: UUID = Field(description="The printer's id.")
    name: str = Field(description="Its name.")
    usage: Usage = Field(description="What it prints.")
    is_active: bool = Field(description="It takes jobs.")


class DeviceOut(Schema):
    id: UUID = Field(description="The device's registration id. The device's own id is never shown: it proves the device.")
    name: str = Field(description="Its name, as the business calls it (Counter till).")
    printers: list[DevicePrinterOut] = Field(description="The printers it reaches and prints for, by name.")
    registered_at: datetime = Field(description="When it was set up to print.")
    registered_by: str = Field(description="Who set it up.")
    last_seen_at: datetime | None = Field(description="When it last asked for a job; none = never yet.")
    this_device: bool = Field(description="It is the device asking.")


class DeviceRegisterIn(Closed):
    name: Name = Field(description="The device's name, as the business calls it: Counter till, Kitchen tablet.")
    printers: list[UUID] = Field(
        max_length=MAX_CLAIM_PRINTERS, description="The active printers this device reaches and prints for (their ids)."
    )


class DeviceRefIn(Closed):
    device_id: UUID = Field(description="The device's registration id (printing.device.list).")


class DeviceUpdateIn(DeviceRefIn):
    name: Name | None = Field(None, description="Its new name.")
    printers: list[UUID] | None = Field(
        None, max_length=MAX_CLAIM_PRINTERS, description="The active printers it reaches from now on (their ids)."
    )

    @model_validator(mode="after")
    def _changes(self):
        if self.name is None and self.printers is None:
            raise ValueError(str(NOTHING_TO_CHANGE_DEVICE))
        return self


class DeviceListIn(PageIn):
    pass


class DeviceGetIn(Closed):
    device: DeviceName = Field(description="The device's own id, as its hello says it (base's /ws/print).")


class DeviceGetOut(Schema):
    device: DeviceOut | None = Field(description="The device set up with that id; none = not set up here, or retired.")
    retired: bool = Field(
        description="It was set up here and retired: it prints nothing, and printing from it does not set it up "
        "again; only setting it up again from the device brings it back."
    )


class PruneOut(Schema):
    count: int = Field(description="The finished jobs this run deleted (printed, cancelled or failed over 30 days ago).")

