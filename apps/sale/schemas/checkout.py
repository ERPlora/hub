"""Schemas of a charge (``sale.sale.complete``, ``sale.checkout.preview``): what it charges, how it is paid, and
its preview with the fiscal breakdown."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, field_validator, model_validator

from apps.customer.tax_ids import InvalidCountry, normalize_country
from apps.sale.schemas.fields import (
    A_BOOKING,
    A_CHECK,
    A_CUSTOMER,
    A_MEMBER,
    A_METHOD,
    CHECK_DISCOUNT_ON_THE_CHECK,
    COMBO_LINES,
    COUNTRY_CODE,
    FIXED_DISCOUNT,
    MAX_LINES,
    MAX_PAYMENTS,
    ONE_SOURCE,
    OPEN_LINES,
    SAY_WHAT_IS_ADDED,
    SAY_WHICH_METHOD,
    SERVICE_LINES,
    AttemptKey,
    Cents,
    CheckLineId,
    Closed,
    DocumentType,
    IdType,
    Percent,
    PositiveCents,
    _text,
)
from apps.sale.schemas.lines import ComboLineIn, OpenLineIn, ProductLineIn, ServiceLineIn
from base.sensitive import COSTS


class ChargeLinesIn(Schema):
    """What is charged: an open check (all its lines, or some) or loose lines (a counter sale)."""

    order_id: UUID | None = Field(None, description="The open check to charge.", json_schema_extra=A_CHECK)
    line_ids: list[CheckLineId] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to charge"),
        description="Only these lines of the check (a partial charge); none = all.",
    )
    lines: list[ProductLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        description="Loose catalog lines (a counter sale).",
    )
    open_lines: list[OpenLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=OPEN_LINES,
        description="Loose open-price lines (a counter sale).",
    )
    service_lines: list[ServiceLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=SERVICE_LINES,
        description="Loose lines of services of the Services app (a counter sale).",
    )
    combo_lines: list[ComboLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=COMBO_LINES,
        description="Loose menus of the Menus app, each with its dishes (a counter sale).",
    )
    discount_percent: Percent = Field(
        Decimal("0"), description="Counter sale only: ticket discount in %."
    )
    discount_amount: Cents = Field(
        0, title=FIXED_DISCOUNT, description="Counter sale only: fixed ticket discount in cents."
    )

    @model_validator(mode="after")
    def _one_source(self):
        loose = bool(self.lines or self.open_lines or self.service_lines or self.combo_lines)
        if (self.order_id is None) == (not loose) or (
            self.order_id is not None and loose
        ):
            raise ValueError(str(ONE_SOURCE))
        # A check's discount lives in the check (set_discount): the charge takes none, so a figure here would be said by
        # «An approval is needed» (approval_figures) and ignored by the charge.
        if self.order_id is not None and (self.discount_percent > 0 or self.discount_amount > 0):
            raise ValueError(str(CHECK_DISCOUNT_ON_THE_CHECK))
        return self


class PreviewIn(ChargeLinesIn):
    model_config = ConfigDict(extra="forbid")


class PaymentIn(Closed):
    method_id: UUID | None = Field(None, description="The payment method's id.", json_schema_extra=A_METHOD)
    method: _text(60, 1) | None = Field(
        None,
        description="Its name or its type (cash, card…), when its id is not known.",
    )
    amount: PositiveCents | None = Field(
        None, description="What this leg pays, in cents; empty = what is left to pay."
    )
    tendered: Cents | None = Field(
        None, description="Cash: what was handed over (the change comes out of it)."
    )
    reference: _text(128) = Field(
        "", description="A free reference of the leg, e.g. the card's authorisation."
    )
    extra: Cents = Field(
        0,
        description="Leave it out: only another app's own step at the charge sheet fills it, never what someone asks.",
    )
    extra_label: _text(60) = Field(
        "", validate_default=True, description="Leave it out: the name of that app's added amount, filled by its step."
    )

    @field_validator("extra_label")
    @classmethod
    def _added_is_named(cls, label: str, info):
        if not info.data.get("extra"):
            return ""
        if not label:
            raise ValueError(str(SAY_WHAT_IS_ADDED))
        return label

    @model_validator(mode="after")
    def _named(self):
        if self.method_id is None and self.method is None:
            raise ValueError(str(SAY_WHICH_METHOD))
        return self


class CompleteIn(ChargeLinesIn):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: AttemptKey = Field(
        description="The attempt's key: born when the charge sheet opens and reused on every retry, so a retry never charges twice."
    )
    order_version: int | None = Field(
        None,
        ge=1,
        title=gettext_noop("Check version"),
        description="The check's version the screen charged; a newer one refuses the charge.",
    )
    payments: list[PaymentIn] = Field(
        default_factory=list,
        max_length=MAX_PAYMENTS,
        description="The tenders; none = all in cash, exact amount.",
    )
    document_type: DocumentType | None = Field(
        None, description="ticket or invoice; the settings' default when empty."
    )
    customer_id: UUID | None = Field(
        None,
        description="The customer's card; charging a check without one, the sale is for the customer the check has.",
        json_schema_extra=A_CUSTOMER,
    )
    customer: _text(200, 1) | None = Field(
        None,
        description="The customer's name, phone or email, when the id is not known.",
    )
    customer_name: _text(200) = Field(
        "", description="Invoice: name or company name (the card's by default)."
    )
    customer_tax_id: _text(32) = Field(
        "", description="Invoice: tax id (the card's by default)."
    )
    customer_address: _text(500) = Field(
        "", description="Invoice: address (the card's by default)."
    )
    customer_country: str = Field(
        "",
        description="Invoice: ISO country code of the customer; empty = the business's.",
    )
    customer_id_type: IdType = Field(
        "",
        description="Invoice abroad: 02 EU VAT, 03 passport, 04 foreign tax id, 05 residence certificate, 06 other, 07 not registered.",
    )
    staff_id: UUID | None = Field(
        None, description="Who served the sale (a member of Staff); empty = who serves the check.", json_schema_extra=A_MEMBER
    )
    appointment_id: UUID | None = Field(
        None, description="Counter sale: the appointment it charges.", json_schema_extra=A_BOOKING
    )
    notes: _text(1000) = Field("", description="Notes of the sale.")

    @field_validator("customer_country")
    @classmethod
    def _country(cls, value: str) -> str:
        # The same ISO 3166-1 list Invoicing's recipient reads: what Sales accepts, Invoicing accepts.
        try:
            return normalize_country(value)
        except InvalidCountry:
            raise ValueError(str(COUNTRY_CODE)) from None


#: What Invoicing answered for the fiscal document of a write (models.FiscalStatus); empty on a sale
#: charged before Sales asked for it.
FiscalStatus = Literal["", "issued", "pending", "unavailable", "none"]


class BreakdownOut(Schema):
    """One entry per fiscal key (tax, regime, qualification, exemption cause, rates) and component: the
    shape Invoicing declares. A sale charged before the key was kept reads as subject VAT."""

    rate_pct: Decimal = Field(description="The rate.")
    label: str = Field(description="vat, or the component's name (surcharge…).")
    tax_type: str = Field("vat", description="The component's tax: vat, surcharge, igic, ipsi…")
    regime: str = Field("01", description="The VAT regime key of the rule (01 = general).")
    qualification: str = Field(
        "subject",
        description="subject, subject_reverse, exempt, not_subject or not_subject_location.",
    )
    exempt_reason: str = Field("", description="The exemption cause (E1–E8) of an exempt key.")
    base: int = Field(description="Taxable base of the key, in cents.", json_schema_extra={"money": True})
    tax: int = Field(description="Tax of this component of the key, in cents.", json_schema_extra={"money": True})


class PreviewLineOut(Schema):
    order_line_id: UUID | None = Field(description="The check's line.")
    name: str = Field(description="Name.")
    quantity: Decimal = Field(description="Quantity.")
    unit: str = Field(description="Unit.")
    unit_price: int = Field(description="Frozen price in cents.", json_schema_extra={"money": True})
    discount_percent: Decimal = Field(description="Line discount in %.")
    is_gift: bool = Field(description="A comp.")
    service_id: UUID | None = Field(description="Services' service, if it is one.")
    paid_by_voucher: bool = Field(description="A voucher session pays it (at 0).")
    voucher_name: str = Field(description="The voucher that pays it.")
    voucher_remaining: int | None = Field(
        description="Sessions the voucher had left after this one when applied; null = unlimited."
    )
    tax_category_key: str = Field(description="Tax category.")
    tax_rate: Decimal = Field(description="Rate applied.")
    net_amount: int = Field(description="Base in cents.", json_schema_extra={"money": True})
    tax_amount: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    line_total: int = Field(description="Total in cents.", json_schema_extra={"money": True})
    modifiers: list[str] = Field(description="The options charged inside the line.")
    is_child: bool = Field(
        description="An option of another tax category, charged on a line of its own under its dish."
    )
    combo_name: str = Field(
        description="The menu this line charges, or a dish of (a menu split per dish); empty otherwise."
    )
    components: list[str] = Field(description="The dishes of a menu charged in one line.")


#: The mark of a charge preview's legal limits: amounts in the currency the law writes them in, which the preview says
#: beside them (``limits_currency``), never the business's (hub#926).
IN_LIMITS_CURRENCY = {"money": True, "currency_in": "limits_currency"}


class PreviewOut(Schema):
    order_id: UUID | None = Field(description="The check valued.")
    order_version: int | None = Field(
        description="Its version: send it with the charge."
    )
    lines_count: int = Field(description="Lines valued.")
    tax_included: bool = Field(description="Prices include VAT.")
    subtotal: int = Field(description="Taxable base in cents.", json_schema_extra={"money": True})
    tax_total: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    discount_amount: int = Field(description="Every discount given, in cents.", json_schema_extra={"money": True})
    discount_percent: Decimal = Field(description="Ticket discount in %.")
    ticket_discount_amount: int = Field(
        description="What the ticket discount (its percent and its fixed amount) takes off this charge, in cents.",
        json_schema_extra={"money": True},
    )
    gift_total: int | None = Field(
        description="Comps at cost, in cents (empty without the costs).", json_schema_extra={"money": True, **COSTS}
    )
    total: int = Field(description="What would be charged, in cents.", json_schema_extra={"money": True})
    breakdown: list[BreakdownOut] = Field(description="Base and tax by fiscal key.")
    lines: list[PreviewLineOut] = Field(description="Each line valued.")
    operation_total: int = Field(
        description="The whole operation the cash limit looks at, in cents: on a check charged in parts, what "
        "it already charged plus all it has left (this charge included); otherwise the total.",
        json_schema_extra={"money": True},
    )
    cash_limit: int | None = Field(
        description="From this operation total on, no cash at all, in cents of limits_currency (Spain: 100000, "
        "1,000.00 EUR); empty = no limit.",
        json_schema_extra=IN_LIMITS_CURRENCY,
    )
    ticket_limit: int | None = Field(
        description="Above this total, only an invoice, in cents of limits_currency (Spain: 300000, 3,000.00 EUR); "
        "empty = no limit.",
        json_schema_extra=IN_LIMITS_CURRENCY,
    )
    limits_currency: str = Field(
        description="The currency (ISO 4217) the law writes both limits in, whatever the business charges in: EUR."
    )


class CheckoutStepOut(Schema):
    key: str = Field(description="«<app>.<step>».")
    app: str = Field(description="The app that adds the step.")
    component: str = Field(description="The component of that app that paints the step, without .vue.")


class CheckoutStepsOut(Schema):
    steps: list[CheckoutStepOut] = Field(
        description="What the apps on add to the charge, between the amount and the tenders, in their order; empty "
        "when none does, and then a charge takes nothing added to its tenders."
    )
