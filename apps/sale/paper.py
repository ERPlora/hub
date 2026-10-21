"""The paper of Sales on the receipt printer (PRINTING-F07, F08, F09; SALE-F21, F29): the receipt of a sale and
the bill of a check as the app of the device paints them (``crates/peripherals/src/escpos.rs``), composed from
the same figures the screen's paper lays out (``ReceiptPaper.vue``, ``PrebillModal.vue``): the header of the
receipt settings (its first line is the name, the rest the address), the number Invoicing gave the sale (its
own while it has none), the lines, the totals, the payment and, with VeriFactu, the fiscal QR. Every figure is
the server's; this only lays them out, in units (the renderer prints major-unit amounts). Pure: no ORM.
"""

from decimal import Decimal

from babel.numbers import format_currency
from django.utils import translation
from django.utils.translation import gettext

from apps.sale.schemas import PreviewOut, SaleOut

#: The legal texts of the fiscal QR (Orden HAC/1177/2024 art. 20.1.b and 21.1; RD 1619/2012 art. 6.5.b): the
#: AEAT fixes them in Spanish, whatever the paper's language.
QR_HEADING = "QR tributario:"
QR_LEGEND = "VERI*FACTU"


def units(amount: int, decimals: int) -> float:
    """``amount`` in the currency's minor unit, as the renderer prints it (12.5, never 1250)."""
    return float(Decimal(amount).scaleb(-decimals))


def _header(text: str) -> list[str]:
    return [line.strip() for line in (text or "").split("\n") if line.strip()]


def _business(header: str) -> dict:
    lines = _header(header)
    business = {"business_name": lines[0] if lines else gettext("My business")}
    if lines[1:]:
        business["business_address"] = "\n".join(lines[1:])
    return business


def _money(amount: int, currency: str, decimals: int) -> str:
    return format_currency(Decimal(amount).scaleb(-decimals), currency, locale=translation.to_locale(translation.get_language() or "en"))


def _item(line, decimals: int) -> dict:
    """A line of a sale (``SaleLineOut``) or of a valued check (``PreviewLineOut``): an option of another tax
    category hangs under its dish («+ …»), a gift says so, a menu in one line lists its dishes and a line a
    voucher paid says it was already paid."""
    child = bool(getattr(line, "parent_line_id", None)) or getattr(line, "is_child", False)
    name = f"{line.name} {gettext('(On the house)')}" if line.is_gift else line.name
    item = {"name": f"+ {name}" if child else name, "quantity": float(line.quantity), "total": units(line.line_total, decimals)}
    if line.modifiers:
        item["modifiers"] = list(line.modifiers)
    if line.components:
        item["components"] = [_dish(dish) for dish in line.components]
    notes = [(line.notes or "").strip()] if hasattr(line, "notes") else []
    if line.paid_by_voucher:
        notes.append(gettext("Already paid · %(name)s") % {"name": line.voucher_name})
    if any(notes):
        item["notes"] = " · ".join(note for note in notes if note)
    return item


def _dish(dish) -> str:
    if isinstance(dish, str):
        return dish
    return f"{dish.quantity}× {dish.product_name}" if dish.quantity > 1 else dish.product_name


def receipt(
    sale: SaleOut,
    *,
    header: str,
    footer: str,
    decimals: int,
    duplicate: bool,
    record: dict | None = None,
    issuer_tax_id: str = "",
    customer_tax_id: str = "",
    customer_address: str = "",
) -> tuple[str, dict]:
    """The document type and the document of ``sale``'s receipt: ``receipt`` for a ticket, ``invoice`` for a
    sale charged as a full invoice (both parties and its breakdown). ``record``: VeriFactu's record of its
    document (``qr_url``), whose QR opens the paper."""
    full = sale.document_type == "invoice"
    document = {
        **_business(header),
        "receipt_id": sale.invoice_number or sale.number,
        "duplicate": duplicate,
        "cashier": sale.created_by,
        "items": [_item(line, decimals) for line in sale.lines],
        "subtotal": units(sale.subtotal, decimals),
        "tax_amount": units(sale.tax_total, decimals),
        "total": units(sale.total, decimals),
        "payment_method": sale.payment_method_name,
        "paid": units(sale.tendered_total, decimals),
        "change": units(sale.change_total, decimals),
    }
    if sale.customer_name:
        document["customer_name"] = sale.customer_name
    if full:
        document.update(
            vat_number=issuer_tax_id,
            customer_tax_id=customer_tax_id,
            tax_breakdown=[
                {"rate": float(row.rate_pct), "base": units(row.base, decimals), "tax": units(row.tax, decimals)}
                for row in sale.breakdown
            ],
        )
        if customer_address:
            document["customer_address"] = customer_address
    # The discount is already inside the amounts: said under them, as on screen, never subtracted again.
    said = []
    if sale.discount_amount > 0:
        said.append(
            gettext("Discount of %(amount)s, already applied to the amounts above.")
            % {"amount": _money(sale.discount_amount, sale.currency, decimals)}
        )
    if (footer or "").strip():
        said.append(footer.strip())
    if said:
        document["receipt_footer"] = "\n".join(said)
    if record and record.get("qr_url"):
        document.update(qr_data=record["qr_url"], qr_heading=QR_HEADING, qr_legend=QR_LEGEND)
    return ("invoice" if full else "receipt"), document


def bill(valued: PreviewOut, *, label: str, header: str, decimals: int) -> dict:
    """The bill of a check (``prebill``): what is owed, without a number, a QR or a payment."""
    document = {
        **_business(header),
        "items": [_item(line, decimals) for line in valued.lines],
        "subtotal": units(valued.subtotal, decimals),
        "tax_amount": units(valued.tax_total, decimals),
        "total": units(valued.total, decimals),
    }
    if label:
        document["customer_name"] = label
    return document
