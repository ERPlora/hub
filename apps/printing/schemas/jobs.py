"""Schemas of the print jobs (``printing.job.*``): asking for one, the queue, its summary and its prune."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import JsonValue, StringConstraints, model_validator

from apps.printing.schemas.fields import (
    A_JOB,
    JOB,
    REFERENCE,
    Closed,
    DocumentType,
    JobFormat,
    JobKey,
    JobKind,
    JobStatus,
    Name,
    PageIn,
    Reason,
    SortDir,
    Usage,
    _text,
)

#: An A4 page is a document with its styles and its QR inline, not a file upload.
MAX_HTML_BYTES = 2 * 1024 * 1024

SAY_WHICH_JOB = _("Say which job: its id or the number of its document.")
A4_NEEDS_PAGE = _("An A4 job carries its A4 page (html).")
PAGE_ONLY_A4 = _("Only an A4 job carries a page: a receipt printer prints the structured document.")
PAGE_TOO_LARGE = _("The A4 page is larger than 2 MB.")
PAGE_WITH_SCRIPT = _("The A4 page cannot carry a script.")
A4_ONCE = _("An A4 page prints once: ask for another job for another copy.")

_SCRIPT = re.compile(r"<\s*script\b", re.IGNORECASE)

WAITS_FOR_DEVICE = (
    "True: nothing has printed it yet, as no device that prints its printer is on now (none is set up in Printing › "
    "Devices, or the ones there gave no news in the last 90 s): it waits in the queue and prints once one is. Say so, "
    "never that it printed."
)


class JobCreateIn(Closed):
    job_key: JobKey | None = Field(
        None,
        json_schema_extra={"attempt_key": True},
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
        title=gettext_noop("Currency"),
        description="The amounts' currency (ISO 4217), for their decimals; without it, the business's.",
    )
    automatic: bool = Field(
        False,
        title=gettext_noop("Automatic print at checkout"),
        description="The print by itself at checkout: it follows «print the receipt at checkout» and «open the drawer "
        "at checkout» of the settings.",
    )
    open_drawer: bool = Field(
        True,
        description="With automatic: false keeps the drawer shut whatever the settings (a checkout with no cash).",
    )
    source_app: _text(32) | None = Field(None, description="The app that asks for it (sale).")
    source_ref: _text(64) | None = Field(
        None, title=REFERENCE, description="The document it is, as a person reads it (T-000123)."
    )

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


class PrinterTestOut(JobOut):
    """The test page queued for its printer."""

    waits_for_device: bool = Field(description=WAITS_FOR_DEVICE)


class JobDetailOut(JobOut):
    """One job as the queue shows it, with its title."""

    label: str = Field(
        description="How the queue titles it, in the reader's language: its document and its number («Receipt "
        "T-000123»), or what it is when it has none («Open the drawer»)."
    )


class JobCreateOut(Schema):
    job: JobOut | None = Field(description="The job queued (or the one already queued with that key); none = nothing.")
    duplicate: bool = Field(description="A job with that key was already in the queue: nothing new was queued.")
    skipped: Literal["print_on_sale_off"] | None = Field(
        description="Why the receipt was not queued: the business does not print it at checkout."
    )
    waits_for_device: bool = Field(description=WAITS_FOR_DEVICE)


class JobListIn(PageIn):
    search: str | None = Field(None, max_length=64, description="Part of the document's number or title.")
    status: JobStatus | None = Field(None, description="Only the jobs in this state.")
    usage: Usage | None = Field(None, description="Only the jobs of this function.")
    printer_id: UUID | None = Field(None, description="Only the jobs of this printer.")
    sort: Literal["created_at", "status", "usage", "attempts"] = Field("created_at", description="Order by.")
    dir: SortDir = Field("desc", description="Ascending or descending.")


class JobRefIn(Closed):
    job_id: UUID | None = Field(None, title=JOB, description="The job's id.", json_schema_extra=A_JOB)
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
        description="Where its next job goes from the device that asks: a receipt to that device's own receipt printer if "
        "any; else the chosen one if active, else its first active one by name; none if no active printer has the function."
    )
    pending: int = Field(description="Its jobs waiting.")
    oldest_pending_at: datetime | None = Field(description="When the oldest of them was queued.")
    sent: int = Field(description="Its jobs a device has and has not confirmed.")
    failed: int = Field(description="Its failed jobs.")
    unattended: int = Field(
        description="Its jobs waiting that no device set up here can print (no device reaches their printer, or a "
        "printer of their function and paper)."
    )
    stalled: int = Field(
        description="Its jobs that have waited a minute or more with no device on to print them, as the bell counts "
        "them: those no device set up here prints, and those whose device gave no news in the last 90 s (off)."
    )
    signed_out: bool = Field(
        description="A device set up for it lost its session because someone entered on another device and the plan "
        "covers no more devices at a time: it prints nothing until someone enters on it again (not a device off)."
    )


class JobSummaryOut(Schema):
    usages: list[UsageSummary] = Field(description="Each function, receipts, kitchen, bar and labels, in that order.")
    pending: int = Field(description="Jobs waiting, every function.")
    sent: int = Field(description="Jobs a device has and has not confirmed, every function.")
    failed: int = Field(description="Failed jobs, every function.")


class PruneOut(Schema):
    count: int = Field(description="The finished jobs this run deleted (printed, cancelled or failed over 30 days ago).")
