"""The printable document: the A4 page of an invoice (``templates/invoice/invoice.html``) in the reader's language."""

from decimal import Decimal

from babel.numbers import format_decimal, format_percent
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext, pgettext_lazy
from django.utils.translation import gettext_lazy as _

from apps.invoice.document_issuer import document_issuer
from apps.invoice.models import Invoice
from apps.invoice.queries.rows import _loaded
from base.business import money_text

# Texts of the printed document (and its titles), in the reader's language.
DOC_INVOICE = _("Invoice")
DOC_SIMPLIFIED = _("Simplified invoice")
DOC_RECTIFYING = _("Rectifying invoice")
DOC_COPY = _("Copy")
TAX_VAT = _("VAT")
TAX_SURCHARGE = _("Equivalence surcharge")
# «Exento» and «No sujeto», as the invoice's screen says them, not taxes' «Exenta» and «No sujeta».
TAX_EXEMPT = pgettext_lazy("invoice", "Exempt")
TAX_EXEMPT_CAUSE = _("Exempt (%(cause)s)")
TAX_NOT_SUBJECT = pgettext_lazy("invoice", "Not subject")
TAX_REVERSE_CHARGE = _("Reverse charge")
WITHHOLDING = pgettext_lazy("invoice", "IRPF withholding %(rate)s")
RECTIFIES_NOTE = _("Rectifies invoice %(number)s. Reason: %(reason)s")
RECTIFIES_NOTE_NO_REASON = _("Rectifies invoice %(number)s.")


def _money(cents: int | Decimal, currency: str, language: str) -> str:
    """Minor units of ``currency`` (12100 is 121.00 €, and ¥12,100: the yen has no cents); a unit price keeps the two
    more decimals the price without VAT may have (0.8264 €)."""
    return money_text(cents, currency, language=language)


def _percent(rate, language: str) -> str:
    return format_percent(
        Decimal(str(rate)) / 100, locale=language, decimal_quantization=False
    )


def _tax_label(item: dict, language: str) -> list[tuple[str, int, int]]:
    """The printed rows of a breakdown entry: ``(label, base, amount)``; a surcharge is its own row."""
    qualification = item["qualification"]
    if qualification == "exempt":
        cause = item.get("exempt_reason", "")
        label = (
            gettext(TAX_EXEMPT_CAUSE) % {"cause": cause}
            if cause
            else str(TAX_EXEMPT)
        )
    elif qualification in ("not_subject", "not_subject_location"):
        label = str(TAX_NOT_SUBJECT)
    elif qualification == "subject_reverse":
        label = gettext(TAX_REVERSE_CHARGE)
    else:
        name = gettext(TAX_VAT) if item["tax"] == "vat" else item["tax"].upper()
        label = f"{name} {_percent(item['rate'], language)}"
    rows = [(label, item["base"], item["quota"])]
    if Decimal(str(item.get("surcharge_rate", "0"))):
        rows.append(
            (
                f"{gettext(TAX_SURCHARGE)} {_percent(item['surcharge_rate'], language)}",
                item["base"],
                item["surcharge_quota"],
            )
        )
    return rows


def _withholding(invoice: Invoice, language: str) -> dict | None:
    """What an invoice prints after its total: what is withheld of it and what is left to collect."""
    if invoice.withholding_rate is None:
        return None
    return {
        "label": WITHHOLDING % {"rate": _percent(invoice.withholding_rate, language)},
        "amount": _money(-invoice.withholding_amount, invoice.currency, language),
        "payable": _money(invoice.payable_amount, invoice.currency, language),
    }


def document_note(invoice: Invoice) -> str:
    """The note of a document in the reader's language: a rectifying one names the invoice it rectifies
    and its reason (composed here: the database keeps no sentence); any other, its own notes."""
    if invoice.rectifies_id:
        reason = invoice.description.strip()
        number = invoice.rectifies.number
        if reason:
            return gettext(RECTIFIES_NOTE) % {"number": number, "reason": reason}
        return gettext(RECTIFIES_NOTE_NO_REASON) % {"number": number}
    return invoice.notes


def render_document(invoice: Invoice, *, duplicate: bool = False, qr: dict | None = None) -> str:
    """The A4 document of an invoice, in the active language (``templates/invoice/invoice.html``); with ``qr``
    (``{"url", "svg"}``), VeriFactu's QR on top, as the AEAT asks (Orden HAC/1177/2024, art. 21)."""
    invoice = _loaded(invoice)
    language = translation.get_language() or "en"
    if invoice.is_rectification:
        title = DOC_RECTIFYING
    elif invoice.invoice_type == "F2":
        title = DOC_SIMPLIFIED
    else:
        title = DOC_INVOICE
    money = lambda cents: _money(cents, invoice.currency, language)  # noqa: E731
    lines = list(invoice.lines.all())
    discounted = any(line.discount_amount for line in lines)
    context = {
        "invoice": invoice,
        "issuer_vat_number": document_issuer(invoice)["issuer_vat_number"],
        "language": language,
        "title": title,
        "duplicate": duplicate,
        "copy_label": DOC_COPY,
        "issue_date": date_format(invoice.issue_date, "SHORT_DATE_FORMAT"),
        "operation_date": date_format(invoice.operation_date, "SHORT_DATE_FORMAT")
        if invoice.operation_date != invoice.issue_date
        else "",
        "due_date": date_format(invoice.due_date, "SHORT_DATE_FORMAT") if invoice.due_date else "",
        # RD 1619/2012 art. 6.1.f: the unit price without VAT and the discount apart, the amount its base.
        "discounted": discounted,
        "lines": [
            {
                "description": line.description,
                "quantity": format_decimal(line.quantity.normalize(), locale=language),
                "unit_price": _money(line.unit_price, invoice.currency, language),
                "discount": money(line.discount_amount) if line.discount_amount else "",
                "tax_rate": _percent(line.tax_rate, language),
                "amount": money(line.base_amount),
            }
            for line in lines
        ],
        "taxes": [
            {"label": label, "base": money(base), "amount": money(amount)}
            for item in invoice.tax_breakdown
            for label, base, amount in _tax_label(item, language)
        ],
        "base": money(invoice.base_amount),
        "total": money(invoice.total_amount),
        "withholding": _withholding(invoice, language),
        "note": document_note(invoice),
        "qr": qr,
    }
    return render_to_string("invoice/invoice.html", context)
