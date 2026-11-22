"""What every write of the invoice app shares: the clock and the business's day, who acts, the answer of an operation
and the logger.
"""

import datetime as dt
import logging

from django.utils import timezone, translation
from live.context import OperationContext

from apps.invoice.models import Invoice
from apps.invoice.queries import invoice_detail
from base.business import business_zone

# One logger for every module of the invoice app's writes, named after the package rather than each module.
logger = logging.getLogger("apps.invoice.services")


def _now() -> dt.datetime:
    return timezone.now()


def _today() -> dt.date:
    return timezone.localdate(_now(), business_zone())


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor or "")[:128]


def _detail(ctx: OperationContext, invoice: Invoice) -> dict:
    with translation.override(ctx.language):
        detail = invoice_detail(invoice)
    # Only the answer of the operation that issued it says what VeriFactu did with it.
    return {**detail, "verifactu_status": getattr(invoice, "verifactu_status", None)}


def _result(
    ctx: OperationContext,
    invoice: Invoice | None,
    *,
    issued: bool,
    already: bool = False,
) -> dict:
    return {
        "issued": issued,
        "already": already,
        "verifactu_status": getattr(invoice, "verifactu_status", None),
        "invoice": _detail(ctx, invoice) if invoice is not None else None,
    }
