"""The printer a job goes to (PRINTING-F04, F22).

A receipt asked for from a till with receipt printers of its own goes to one of them, and so does its drawer: the
one chosen in the settings if it is one of them, else the first by name. Any other paper, and a receipt asked for
from anywhere else (a device with none of its own, the assistant, an API key), goes to the business's printer of its
function: the one chosen in the settings, else the first active one by name. A till is known by the key of the id its
app sends with every request (``this_device_key``).
"""

import uuid

from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.db.models.functions import Lower

# The package's own helpers: it imports this module first, so they are read when a job is queued.
from apps.printing import queries
from apps.printing.models import PrintDevice, Printer, PrintJob, Settings, Usage

#: Receipt paper before the computer's printer, the order a job of a function finds its printer in.
_SYSTEM_LAST = Case(When(kind=Printer.Kind.SYSTEM, then=Value(1)), default=Value(0), output_field=IntegerField())


def _own_receipt_printers(device: str, chosen_id: uuid.UUID | None) -> QuerySet[Printer]:
    """The active receipt printers on receipt paper of the till set up with the key ``device`` and not retired, the
    one chosen in the settings first and then by name; none for a device not set up here.

    Its printers come by a subquery, not a join: the lock that holds the printer until its job is saved would take
    the till's row too, and the till claiming its jobs would wait for the checkout."""
    reached = PrintDevice.printers.through.objects.filter(printdevice__key=device, printdevice__retired_at__isnull=True)
    printers = Printer.objects.filter(pk__in=reached.values("printer_id"), is_active=True, usage=Usage.RECEIPT)
    chosen_first = Case(When(pk=chosen_id, then=Value(0)), default=Value(1), output_field=IntegerField())
    return printers.exclude(kind=Printer.Kind.SYSTEM).order_by(chosen_first, Lower("name"), "id")


def job_printer(usage: str, paper: str, settings: Settings, device: str | None = None) -> Printer | None:
    """The printer a job of ``usage`` on ``paper`` goes to, asked for from the till with the key ``device`` (none: the
    business's printer). It is held until the job that names it is saved: a deletion waits for it, and one deleted
    before is passed over."""
    chosen_id = getattr(settings, f"{queries.DEFAULT_FIELDS[usage]}_id")
    if device is not None and usage == Usage.RECEIPT and paper == PrintJob.Format.RECEIPT:
        own = queries.first_held(_own_receipt_printers(device, chosen_id))
        if own is not None:
            return own
    printers = Printer.objects.filter(is_active=True)
    if paper == PrintJob.Format.A4:
        printers = printers.filter(kind=Printer.Kind.SYSTEM)
    else:
        printers = printers.exclude(kind=Printer.Kind.SYSTEM)
    chosen = queries.first_held(printers.filter(pk=chosen_id)) if chosen_id else None
    return chosen or queries.first_held(printers.filter(usage=usage).order_by(Lower("name"), "id"))


def active_printers() -> dict[str, list[Printer]]:
    """The active printers of each function: receipt paper first, then the computer's, by name within each."""
    active: dict[str, list[Printer]] = {}
    for printer in Printer.objects.filter(is_active=True).order_by(_SYSTEM_LAST, Lower("name"), "id"):
        active.setdefault(printer.usage, []).append(printer)
    return active


def prints_on(usage: str, chosen: Printer | None, active: list[Printer], device: str | None) -> Printer | None:
    """The printer a job of ``usage`` goes to from the till with the key ``device``, as the summary tells it (a read:
    nothing is held). ``chosen`` is the settings' choice and ``active`` the function's active printers in order."""
    if device is not None and usage == Usage.RECEIPT:
        own = _own_receipt_printers(device, chosen.id if chosen else None).first()
        if own is not None:
            return own
    return chosen if chosen is not None and chosen.is_active else (active[0] if active else None)
