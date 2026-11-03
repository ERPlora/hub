"""The paper of Sales on the receipt printer (PRINTING-F07, F08, F09; SALE-F21, F29): the receipt of a sale and
the bill of a check as the app of the device paints them (``crates/peripherals/src/escpos.rs``), composed from
the same figures the screen's paper lays out (``ReceiptPaper.vue``, ``PrebillModal.vue``): the business as
``letterhead`` names it, the number Invoicing gave the sale (its own while it has none), the lines, the totals,
the payment and, with VeriFactu, the fiscal QR. Every figure is the server's; this only lays them out, in units
(the renderer prints major-unit amounts). Pure: no ORM.
"""

from decimal import Decimal

from django.utils.translation import gettext

from apps.sale.schemas import PreviewOut, SaleOut
from base.business import money_text

#: The legal texts of the fiscal QR (Orden HAC/1177/2024 art. 20.1.b and 21.1; RD 1619/2012 art. 6.5.b): the
#: AEAT fixes them in Spanish, whatever the paper's language.
QR_HEADING = "QR tributario:"
QR_LEGEND = "VERI*FACTU"


def units(amount: int, decimals: int) -> float:
    """``amount`` in the currency's minor unit, as the renderer prints it (12.5, never 1250)."""
    return float(Decimal(amount).scaleb(-decimals))


def _header(text: str) -> list[str]:
    return [line.strip() for line in (text or "").split("\n") if line.strip()]


def letterhead(issuer: dict | None, *, header: str, registered_name: str = "") -> dict:
    """The business as every paper of the till names it (hub#458; RD 1619/2012, arts. 6 and 7): ``issuer``
    (``name``, ``tax_id``, ``address``) heads it and the receipt header goes under it as an addition, without what
    the issuer already said. Without an issuer the header is all there is: its first line is the name and the rest
    the address; without either, the name the business registered."""
    added = _header(header)
    if issuer is None:
        return {"name": added[0] if added else registered_name or gettext("My business"), "tax_id": "", "lines": added[1:]}
    said = {issuer["name"].casefold(), issuer["address"].casefold()}
    address = [issuer["address"]] if issuer["address"] else []
    return {
        "name": issuer["name"],
        "tax_id": issuer["tax_id"],
        "lines": [*address, *(line for line in added if line.casefold() not in said)],
    }


def _business(name: str, lines: list[str]) -> dict:
    business = {"business_name": name}
    if lines:
        business["business_address"] = "\n".join(lines)
    return business


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
    letterhead: dict,
    footer: str,
    decimals: int,
    duplicate: bool,
    record: dict | None = None,
) -> tuple[str, dict]:
    """The document type and the document of ``sale``'s receipt: ``receipt`` for a ticket, ``invoice`` for a
    sale charged as a full invoice (both parties and its breakdown). ``record``: VeriFactu's record of its
    document (``qr_url``), whose QR opens the paper."""
    full = sale.document_type == "invoice"
    document = {
        **_business(letterhead["name"], letterhead["lines"]),
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
    if letterhead["tax_id"]:
        document["vat_number"] = letterhead["tax_id"]
    if sale.customer_name:
        document["customer_name"] = sale.customer_name
    if full:
        document.update(
            customer_tax_id=sale.customer_tax_id,
            tax_breakdown=[
                {"rate": float(row.rate_pct), "base": units(row.base, decimals), "tax": units(row.tax, decimals)}
                for row in sale.breakdown
            ],
        )
        if sale.customer_address:
            document["customer_address"] = sale.customer_address
    # The discount is already inside the amounts: said under them, as on screen, never subtracted again.
    said = []
    if sale.discount_amount > 0:
        said.append(
            gettext("Discount of %(amount)s, already applied to the amounts above.")
            % {"amount": money_text(sale.discount_amount, sale.currency)}
        )
    if (footer or "").strip():
        said.append(footer.strip())
    if said:
        document["receipt_footer"] = "\n".join(said)
    if record and record.get("qr_url"):
        document.update(qr_data=record["qr_url"], qr_heading=QR_HEADING, qr_legend=QR_LEGEND)
    return ("invoice" if full else "receipt"), document


def bill(valued: PreviewOut, *, label: str, letterhead: dict, decimals: int) -> dict:
    """The bill of a check (``prebill``): what is owed, without a number, a QR or a payment. The app's bill prints no
    ``vat_number`` (``render_prebill``), so the tax ID travels as the last line of the address."""
    tax_id = [gettext("Tax ID: %(tax_id)s") % {"tax_id": letterhead["tax_id"]}] if letterhead["tax_id"] else []
    document = {
        **_business(letterhead["name"], [*letterhead["lines"], *tax_id]),
        "items": [_item(line, decimals) for line in valued.lines],
        "subtotal": units(valued.subtotal, decimals),
        "tax_amount": units(valued.tax_total, decimals),
        "total": units(valued.total, decimals),
    }
    if label:
        document["customer_name"] = label
    return document
