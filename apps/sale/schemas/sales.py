"""Schemas of a sale charged: its lines, tenders and paper, and how it is named, found, listed, printed and voided."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.sale.schemas.checkout import BreakdownOut, FiscalStatus
from apps.sale.schemas.fields import (
    A_SALE,
    SAY_WHICH_SALE,
    AttemptKey,
    Cents,
    Closed,
    DocumentType,
    MethodType,
    Page,
    PageIn,
    Reason,
    SaleStatus,
    SortDir,
    _text,
)
from base.sensitive import COSTS


class SaleDishOut(Schema):
    product_id: UUID = Field(description="The dish's product (Inventory).")
    product_name: str = Field(description="Its name.")
    quantity: int = Field(description="How many in one menu.")
    modifiers: list[str] = Field(
        default_factory=list, description="The options of Modifiers charged inside it, as the receipt names them."
    )


class SaleLineOut(Schema):
    id: UUID = Field(description="The line's id.")
    position: int = Field(description="Its place.")
    order_line_id: UUID | None = Field(description="The check's line it came from.")
    product_id: UUID | None = Field(description="Inventory's product.")
    department_id: UUID | None = Field(description="The open price's department.")
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU.")
    is_service: bool = Field(description="A service.")
    unit: str = Field(description="Unit.")
    quantity: Decimal = Field(description="Quantity.")
    unit_price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit.", json_schema_extra={"money": True}
    )
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: str = Field(description="Unit the price refers to.")
    discount_percent: Decimal = Field(description="Line discount in %.")
    is_gift: bool = Field(description="A comp.")
    gift_reason: str = Field(description="Why.")
    notes: str = Field(description="Note.")
    staff_id: UUID | None = Field(description="Who served it.")
    service_id: UUID | None = Field(description="Services' service, if it is one.")
    paid_by_voucher: bool = Field(description="A voucher session paid it (at 0).")
    voucher_name: str = Field(description="The voucher that paid it.")
    tax_category_key: str = Field(description="Tax category.")
    tax_rate: Decimal = Field(description="Rate.")
    tax_country_code: str = Field(description="Country of the rule.")
    tax_region_code: str = Field(
        description="Region of the rule; empty = the whole country."
    )
    tax_rule_id: UUID | None = Field(description="Tax's rule.")
    net_amount: int = Field(description="Base in cents.", json_schema_extra={"money": True})
    tax_amount: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    line_total: int = Field(description="Total in cents.", json_schema_extra={"money": True})
    returned_quantity: Decimal = Field(description="Units that came back with refunds.")
    modifiers: list[str] = Field(
        description="The options charged inside the line, as the receipt prints them under it."
    )
    parent_line_id: UUID | None = Field(
        description="The line of the dish an option of another tax category hangs from."
    )
    combo_id: UUID | None = Field(description="The menu of Menus this line charges, or a dish of.")
    combo_name: str = Field(description="That menu's name: the receipt's header of its dishes.")
    components: list[SaleDishOut] = Field(description="The dishes of the menu charged in this line.")


class SalePaymentOut(Schema):
    id: UUID = Field(description="The leg's id.")
    position: int = Field(description="Order taken.")
    method_id: UUID = Field(description="Payment method.")
    method_name: str = Field(
        description="Its name as charged (translated if it is a factory one)."
    )
    method_type: MethodType = Field(description="cash, card, transfer or other.")
    amount: int = Field(description="Amount in cents.", json_schema_extra={"money": True})
    tendered: int = Field(description="Handed over, in cents.", json_schema_extra={"money": True})
    change: int = Field(description="Change given, in cents.", json_schema_extra={"money": True})
    reference: str = Field(description="Reference.")
    extra: int = Field(description="What another app added to this leg (a tip), in cents: never part of the sale.", json_schema_extra={"money": True})
    extra_label: str = Field(description="What that added amount is (e.g. «Tip»); empty when nothing was added.")


class PaperOut(Schema):
    queued: bool = Field(
        description="True: Printing queued it for its printer. False, only for the charge's own paper: Printing is "
        "not on, no printer takes it, its fiscal document is still pending or Printing refused it — the device prints "
        "the screen's paper. A reprint or a bill that is not queued fails and says why."
    )
    job_id: UUID | None = Field(description="Its job in the printing queue.")
    printer: str | None = Field(description="The printer it went to.")
    waits_for_device: bool = Field(
        description="True: queued, but nothing has come out yet, as no device that prints that printer is on now (none "
        "is set up in Printing › Devices, or the ones there gave no news in the last 90 s): it waits in the queue and "
        "prints once one is."
    )


class LetterheadIn(Schema):
    sale_id: UUID | None = Field(
        None, description="The sale whose paper it heads: its fiscal document's issuer. None: today's, for a bill."
    )


class LetterheadOut(Schema):
    sale_id: UUID | None = Field(description="The sale it was asked for, if any.")
    name: str = Field(description="The business's name on paper: the issuer's legal name.")
    tax_id: str = Field(
        description="The business's tax ID as the paper prints it (ESB12345674 while registered for intra-EU "
        "operations, ROI); empty without an issuer."
    )
    lines: list[str] = Field(description="What goes under the name: the address, then the receipt header's lines.")


class SaleOut(Schema):
    id: UUID = Field(description="The sale's id.")
    number: str = Field(description="Its number, AAAAMMDD-NNNN.")
    business_day: date = Field(description="Its business day.")
    status: SaleStatus = Field(description="completed, voided or refunded.")
    document_type: DocumentType = Field(description="ticket or invoice.")
    order_id: UUID | None = Field(description="The check it came from.")
    customer_id: UUID | None = Field(description="The customer's card.")
    customer_name: str = Field(description="The customer's name as printed.")
    customer_tax_id: str = Field(description="The recipient's tax ID, on a full invoice; empty on a ticket.")
    customer_address: str = Field(description="The recipient's address, on a full invoice; empty on a ticket.")
    staff_id: UUID | None = Field(description="Who served it.")
    appointment_id: UUID | None = Field(description="The appointment it charged.")
    tax_included: bool = Field(description="Prices include VAT.")
    currency: str = Field(description="ISO 4217 currency it was charged in: the business's then, never rewritten.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    subtotal: int = Field(description="Taxable base in cents.", json_schema_extra={"money": True})
    tax_total: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    discount_amount: int = Field(description="Every discount given, in cents.", json_schema_extra={"money": True})
    gift_total: int | None = Field(
        description="Comps at cost, in cents (empty without the costs).", json_schema_extra={"money": True, **COSTS}
    )
    total: int = Field(description="Total charged, in cents.", json_schema_extra={"money": True})
    tendered_total: int = Field(description="Handed over, in cents.", json_schema_extra={"money": True})
    change_total: int = Field(description="Change given, in cents.", json_schema_extra={"money": True})
    refunded_total: int = Field(description="Refunded so far, in cents.", json_schema_extra={"money": True})
    refundable_total: int = Field(
        description="What can still be refunded, in cents.",
        json_schema_extra={"money": True},
    )
    sessions_to_return: int = Field(
        description="Lines paid with a voucher whose session has not come back yet."
    )
    payment_method_name: str = Field(
        description="The methods it was paid with, once each in the order they were tendered («Cash + Card»)."
    )
    breakdown: list[BreakdownOut] = Field(description="Base and tax by fiscal key.")
    notes: str = Field(description="Notes.")
    voided_at: datetime | None = Field(description="When it was voided.")
    voided_by: str = Field(description="Who voided it.")
    void_reason: str = Field(description="Why.")
    created_at: datetime = Field(description="When it was charged.")
    created_by: str = Field(description="Who charged it.")
    lines: list[SaleLineOut] = Field(description="Its lines.")
    payments: list[SalePaymentOut] = Field(description="Its tenders.")
    invoice_status: FiscalStatus = Field(
        description="Its fiscal document, issued by Invoicing in the same charge: issued; pending (Invoicing "
        "refused now, e.g. no issuer yet, and issues it later on its own); unavailable (no Invoicing: a "
        "ticket without fiscal document)."
    )
    invoice_id: UUID | None = Field(description="Its fiscal document in Invoicing.")
    invoice_number: str = Field(
        description="The number of its fiscal document in its series (TICKET-2026-000001, FACT-2026-000001); "
        "empty while it has none. The paper prints it."
    )
    invoice_type: str = Field(description="F2 (ticket) or F1 (invoice); empty while it has none.")
    receipt_code: str | None = Field(
        description="The code its ticket prints under a QR of its own, for the customer to ask for the full invoice "
        "on the business's public page; none for a full invoice or without Invoicing."
    )
    void_invoice_status: FiscalStatus = Field(
        description="The rectifying invoice of its void, as Invoicing answered; empty if not voided."
    )
    void_invoice_number: str = Field(description="The number of the rectifying invoice of its void.")
    documents_pending: bool = Field(
        description="A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it."
    )
    already: bool = Field(
        False,
        description="True: this attempt had already been charged; nothing new was recorded.",
    )
    printed: PaperOut | None = Field(
        None,
        description="The charge only: whether its receipt (or the drawer's order) went to the printing queue, to "
        "which printer; not queued, the device prints the screen's paper.",
    )


class SaleRefIn(Closed):
    sale_id: UUID | None = Field(None, description="The sale's id.", json_schema_extra=A_SALE)
    sale: _text(24, 1) | None = Field(
        None, description="Its number, e.g. 20261014-0007, when the id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.sale_id is None and self.sale is None:
            raise ValueError(str(SAY_WHICH_SALE))
        return self


class SalePrintIn(SaleRefIn):
    duplicate: bool = Field(
        True,
        title=gettext_noop("Print as duplicate"),
        description="Print it marked «DUPLICATE»: every print from Sales is a copy; only the till's first paper right "
        "after charging, when nothing printed it at checkout, is the original.",
    )


class SaleByKeyIn(Closed):
    idempotency_key: AttemptKey = Field(
        description="The attempt's key the charge was sent with."
    )


class SaleByKeyOut(Schema):
    found: bool = Field(description="Whether a sale was charged with that key.")
    sale: SaleOut | None = Field(description="That sale.")


class SaleListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the number or of the customer's name.",
    )
    status: SaleStatus | None = Field(None, description="Only sales of this status.")
    payment_method_name: str | None = Field(
        None, max_length=60, description="Only sales paid with this method, in full or in part."
    )
    customer_name: str | None = Field(
        None, max_length=200, description="Part of the customer's name."
    )
    customer_id: UUID | None = Field(None, description="Only this customer's sales.")
    staff_id: UUID | None = Field(
        None, description="Only sales served by this member of Staff."
    )
    number: str | None = Field(None, max_length=24, description="Part of the number.")
    date_from: date | None = Field(
        None, description="From this business day (inclusive)."
    )
    date_to: date | None = Field(
        None, description="Up to this business day (inclusive)."
    )
    total_min: Cents | None = Field(None, description="Total at least, in cents.")
    total_max: Cents | None = Field(None, description="Total at most, in cents.")
    sort: Literal[
        "created_at",
        "number",
        "total",
        "customer_name",
        "status",
        "payment_method_name",
    ] = Field("created_at", description="Column to sort by.")
    dir: SortDir = Field("desc", description="Sort direction.")


class SaleRow(Schema):
    id: UUID = Field(description="The sale's id.")
    number: str = Field(description="Number.")
    business_day: date = Field(description="Business day.")
    created_at: datetime = Field(description="When it was charged.")
    status: SaleStatus = Field(description="completed, voided or refunded.")
    document_type: DocumentType = Field(description="ticket or invoice.")
    customer_id: UUID | None = Field(description="Customer's card.")
    customer_name: str = Field(description="Customer's name.")
    payment_method_name: str = Field(
        description="The methods it was paid with, once each in the order they were tendered («Cash + Card»)."
    )
    payment_methods: list[str] = Field(
        description="The same methods one by one, to find the sale by any of them («Cash», «Card»)."
    )
    staff_id: UUID | None = Field(description="Who served it.")
    currency: str = Field(description="ISO 4217 currency it was charged in.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    total: int = Field(description="Total in cents.", json_schema_extra={"money": True})
    tax_total: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    refunded_total: int = Field(description="Refunded in cents.", json_schema_extra={"money": True})
    refundable_total: int = Field(description="Still refundable, in cents.", json_schema_extra={"money": True})
    sessions_to_return: int = Field(
        description="Lines paid with a voucher whose session has not come back yet."
    )
    has_refunds: bool = Field(
        description="It has a refund, also one of no money (a voucher's session): it is refunded, never voided."
    )
    invoice_status: FiscalStatus = Field(
        description="Its fiscal document: issued, pending, unavailable or none; empty before Sales asked for it."
    )
    documents_pending: bool = Field(
        description="A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it."
    )


SalePage = Page[SaleRow]


class VoidIn(SaleRefIn):
    reason: Reason = Field(description="Why the sale is voided (mandatory).")
