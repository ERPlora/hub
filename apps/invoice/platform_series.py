"""The series of ERPlora's own business that erplora.com numbers (INVOICE-F23): the business issues nothing in them by hand,
nor keeps them, and what erplora.com issued is corrected there.
"""

import re

from django.utils.translation import gettext_lazy as _
from live.context import Scope
from live.errors import Conflict

from apps.invoice.models import Invoice
from base.operations import is_platform_hub

#: The code of each one and the type it is born with.
PLATFORM_SERIES_TYPES = {"ERP": "F1", "ERPR": "R1"}
#: A number as erplora.com gives it (``ERP-2026-00123``), in any case: «erp-2026-00123» reads as the same invoice.
_PLATFORM_NUMBER = re.compile(rf"(?:{'|'.join(PLATFORM_SERIES_TYPES)})-\d{{4}}-\d+", re.IGNORECASE)


SERIES_CLOSED = _("erplora.com numbers the ERP and ERPR series: use another series.")


INVOICE_CLOSED = _(
    "erplora.com issued this invoice and corrects it, in its ERPR series: it cannot be corrected by hand here."
)


def platform_codes(scope: Scope) -> tuple[str, ...]:
    """The codes of the series erplora.com numbers: none in any other business, whose ERP is a series like the rest."""
    return tuple(PLATFORM_SERIES_TYPES) if is_platform_hub(scope) else ()


def refuse_platform_series(scope: Scope, code: str, *, field: str = "") -> None:
    """A ``Conflict`` (under ``field``, if it is about one) when ``code`` is a series erplora.com numbers."""
    if code in platform_codes(scope):
        raise _closed(field)


def refuse_platform_number(scope: Scope, number: str, *, field: str) -> None:
    """The same for a ``number`` printed as erplora.com's, whatever the code of its series."""
    if is_platform_hub(scope) and _PLATFORM_NUMBER.fullmatch(number):
        raise _closed(field)


def refuse_platform_invoice(invoice: Invoice) -> None:
    """A ``Conflict`` when erplora.com issued ``invoice``: only its credit note corrects it."""
    if invoice.platform_ref is not None:
        raise Conflict(str(INVOICE_CLOSED), code="invoice.platform_invoice_closed")


def _closed(field: str) -> Conflict:
    message = str(SERIES_CLOSED)
    return Conflict(message, code="invoice.platform_series_closed", fields={field: message} if field else None)
