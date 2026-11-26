"""Asking for a print (PRINTING-F05, F07–F13, F16): a job goes into the queue, to the printer of its function or to
the one it names; a test page is a job of its printer."""

import uuid

from django.db import IntegrityError
from django.template.loader import render_to_string
from django.utils import timezone, translation
from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import UnknownOperation, atomic, operation
from live.operations import get as operation_named

from apps.printing import documents
from apps.printing.models import Printer, PrintJob
from apps.printing.queries.device_reads import this_device_key
from apps.printing.queries.job_printer import job_printer
from apps.printing.queries.jobs import actor, job_row
from apps.printing.queries.printers import find_printer
from apps.printing.queries.settings import current_settings
from apps.printing.queries.waiting import waits_for_device
from apps.printing.schemas.jobs import JobCreateIn, JobCreateOut, PrinterTestOut
from apps.printing.schemas.printers import PrinterRefIn
from base import operations as platform
from base.business import business_zone
from apps.printing.services.writes import _queued

TEST_INACTIVE = _("That printer is inactive: activate it to test it.")
JOB_PRINTER_INACTIVE = _("That printer is inactive: activate it or print on another one.")
JOB_PRINTER_INCOMPATIBLE = _(
    "That printer cannot print this paper: A4 pages go to the system printer and receipts to a receipt printer."
)
TEST_PAGE = _("Test page")


def _given_printer(ref: str, paper: str) -> Printer:
    """The printer a job is sent to by its name or id, held until the job is saved: a deletion waits for it."""
    printer = find_printer(None, ref, hold=True)
    if not printer.is_active:
        raise Conflict(str(JOB_PRINTER_INACTIVE), code="printing.printer_inactive")
    if printer.format != paper:
        raise Conflict(str(JOB_PRINTER_INCOMPATIBLE), code="printing.printer_incompatible")
    return printer


def _stamped(ctx: OperationContext, data: JobCreateIn) -> dict:
    """The document with the envelope the paper needs when the caller left it out: its language (the
    caller's) and, but on a generic document (which prints every key), its money scale: the decimals of the
    caller's currency or, when it does not say, of the business's."""
    document = dict(data.document)
    if data.format != PrintJob.Format.RECEIPT:
        return document
    document.setdefault("locale", ctx.language)
    if data.document_type != "generic" and "decimals" not in document:
        document["decimals"] = get_currency_precision(data.currency or platform.business_currency(ctx.scope))
    return document


def _business_name(ctx: OperationContext) -> str:
    """The business's legal name as Invoicing keeps it, by its operation; empty when Invoicing is not here,
    not on, not set up or not open to this person (the test page then says «ERPlora»)."""
    try:
        issuer = operation_named("invoice.issuer.get")
        found = issuer(ctx, issuer.input.model_validate({}))
    except (UnknownOperation, OperationError):
        return ""
    return found.legal_name


def _new_job(ctx: OperationContext, **values) -> PrintJob:
    """Writes the job unless its key is already in the queue (two at once write one)."""
    try:
        with atomic():
            return PrintJob.objects.create(created_by=actor(ctx), **values)
    except IntegrityError:
        existing = PrintJob.objects.filter(job_key=values["job_key"]).first()
        if existing is None:
            raise
        existing.duplicate = True
        return existing


@operation(
    "printing.job.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.print",
    input=JobCreateIn,
    output=JobCreateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "print this receipt on the Till printer",
                "print the label of this product",
                "send this document to the kitchen printer",
            ),
            "es": (
                "imprime este ticket en la impresora de la caja",
                "imprime la etiqueta de este producto",
                "manda este documento a la impresora de cocina",
            ),
        },
        "description": "Print a document: put it in the print queue, where the device next to its printer prints it. "
        "The document is structured (a receipt: business_name, receipt_id, items [{name, quantity, total}], totals, "
        "payment; a barcode label: product_name, barcode, price) and goes to the printer of its function, or to a "
        "printer named («print it on Kitchen»). The same job_key twice is one job.",
        "risk": "normal",
    },
)
def create_job(ctx: OperationContext, data: JobCreateIn) -> dict:
    # An A4 page carries its own content: the receipt printer's checks are for the structured document.
    problem = documents.problems(data.document_type if data.format == "receipt" else "generic", data.document)
    if problem:
        raise InvalidPayload(problem, fields={"document": problem})
    job_key = data.job_key or f"job-{uuid.uuid7()}"
    existing = PrintJob.objects.select_related("printer").filter(job_key=job_key).first()
    if existing is not None:
        return _answer(existing, duplicate=True)
    job, skipped = _queue_job(ctx, data, job_key)
    if job is None:
        return {"job": None, "duplicate": False, "skipped": skipped, "waits_for_device": False}
    if getattr(job, "duplicate", False):
        return _answer(job, duplicate=True)
    _queued(ctx, job)
    return _answer(job, duplicate=False, skipped=skipped)


def _answer(job: PrintJob, *, duplicate: bool, skipped: str | None = None) -> dict:
    return {"job": job_row(job), "duplicate": duplicate, "skipped": skipped, "waits_for_device": waits_for_device(job)}


def _queue_job(ctx: OperationContext, data: JobCreateIn, job_key: str) -> tuple[PrintJob | None, str | None]:
    """The job ``data`` asks for, written under ``job_key``, and why its receipt was left out, if it was: at checkout
    with the receipt off, only the drawer's kick travels, and nothing at all without cash to open it for."""
    settings = current_settings()
    usage = data.usage or documents.default_usage(data.document_type)
    if data.printer is not None:
        printer = _given_printer(data.printer, data.format)
    else:
        printer = job_printer(usage, data.format, settings, this_device_key(ctx))
    reference = (data.source_ref or documents.reference(data.document))[:64]
    document = _stamped(ctx, data)
    common = {
        "job_key": job_key,
        "usage": usage,
        "printer": printer,
        "reference": reference,
        "source_app": data.source_app or "",
    }
    # The drawer opens at checkout when the settings say so and the till took cash.
    drawer = data.automatic and data.open_drawer and settings.open_drawer_on_sale
    if data.automatic and not settings.print_receipt_on_sale:
        if not drawer:
            return None, "print_on_sale_off"
        # The receipt stays in the drawer's printer's tray: only the kick travels.
        return _new_job(ctx, kind=PrintJob.Kind.DRAWER, open_drawer=True, **common), "print_on_sale_off"
    job = _new_job(
        ctx,
        kind=PrintJob.Kind.DOCUMENT,
        document_type=data.document_type,
        document=document,
        html=data.html or "",
        format=data.format,
        copies=_copies(data, settings),
        open_drawer=drawer,
        **common,
    )
    return job, None


def _copies(data: JobCreateIn, settings) -> int:
    """An A4 page prints once (a copy would be a second original); a receipt takes the settings' copies."""
    if data.format == PrintJob.Format.A4:
        return 1
    return data.copies or (settings.receipt_copies if data.document_type == "receipt" else 1)


@operation(
    "printing.printer.test",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.print",
    input=PrinterRefIn,
    output=PrinterTestOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "print a test page on the Caja 2 printer",
                "test the kitchen printer",
                "send a test ticket to the Till printer",
            ),
            "es": (
                "saca una página de prueba en la impresora Caja 2",
                "prueba la impresora de cocina",
                "manda un ticket de prueba a la impresora de la caja",
            ),
        },
        "description": "Print a test page on a printer, named by its name or id («test the kitchen printer»): the device "
        "next to it prints the sheet with the printer's address and the time, or an A4 page on the system printer. When "
        "the answer says no device that prints that printer is on, say the page stays in that printer's queue until a "
        "device set up in Printing › Devices prints it, never that it printed.",
        "risk": "normal",
    },
)
def test_printer(ctx: OperationContext, data: PrinterRefIn) -> dict:
    # Held until its test page is saved: a deletion waits for it.
    printer = find_printer(data.printer_id, data.printer, hold=True)
    if not printer.is_active:
        raise Conflict(str(TEST_INACTIVE), code="printing.printer_inactive")
    # Read before any write of this command (a query runs READ ONLY).
    business_name = _business_name(ctx)
    page = {"locale": ctx.language, **({"business_name": business_name} if business_name else {})}
    html = ""
    if printer.format == PrintJob.Format.A4:
        with translation.override(ctx.language):
            html = render_to_string(
                "printing/test_page.html",
                {
                    "printer": printer.name,
                    "business": business_name or "ERPlora",
                    # Without its zone: a template would show an aware time on Django's current one.
                    "when": timezone.localtime(timezone.now(), business_zone()).replace(tzinfo=None),
                    "language": ctx.language,
                },
            )
    job = _new_job(
        ctx,
        job_key=f"test-{uuid.uuid7()}",
        kind=PrintJob.Kind.TEST_PAGE,
        document=page,
        html=html,
        format=printer.format,
        usage=printer.usage,
        printer=printer,
        reference=printer.name[:64],
    )
    _queued(ctx, job)
    return {**job_row(job), "waits_for_device": waits_for_device(job)}
