"""Input and output schemas of the cart_checkout app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels in
whole minor units of the cart's currency (as many decimals as it has: 1250 is 12.50 zł, ¥1,250) and quantities as decimals with up to three
places. A cart is named by its id or, as a person says it (assistant, voice), by its session code or its
customer's email or name; an order by its id or its number (``OS-20261014-0003``); a line by its id.
Every input refuses a field it does not declare.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import AfterValidator, ConfigDict, StringConstraints, field_validator, model_validator

from apps.cart_checkout.models import (
    EMAIL_MAX_LENGTH,
    METHOD_MAX_LENGTH,
    NAME_MAX_LENGTH,
    REASON_MAX_LENGTH,
    SESSION_MAX_LENGTH,
    SKU_MAX_LENGTH,
)

T = TypeVar("T")

#: Ninety-nine billion units of a currency with two decimals: far above any cart, inside a bigint.
MAX_AMOUNT = 9_999_999_999_999
#: The most units one line may carry: a million, far above any cart, so a sum never leaves a bigint.
MAX_QUANTITY = 1_000_000
NOTES_MAX_LENGTH = 2000
#: How many free fields an address or a line's variant may carry, and how long each value is.
MAX_FREE_FIELDS = 20
FREE_VALUE_MAX_LENGTH = 255

EMAIL_INVALID = _("Enter a valid email.")
CURRENCY_UNKNOWN = _("That is not a currency code (ISO 4217, such as EUR).")
EXPIRY_PASSED = _("The expiry must be in the future.")
QUANTITY_NOT_POSITIVE = _("The quantity must be greater than 0.")
REASON_REQUIRED = _("Say why the order failed: the reason stays on the order.")
SAY_WHICH_CART = _("Say which cart: its id, its session code, or its customer's email or name.")
SAY_WHICH_ORDER = _("Say which order: its id, or its number.")

CartStatus = Literal["active", "abandoned", "converted", "expired"]
OrderStatus = Literal["initiated", "paid", "failed", "completed"]
CartSort = Literal[
    "session_token", "-session_token",
    "customer_email", "-customer_email",
    "customer_name", "-customer_name",
    "status", "-status",
    "total_items", "-total_items",
    "total_amount", "-total_amount",
    "currency", "-currency",
    "expires_at", "-expires_at",
    "last_activity_at", "-last_activity_at",
    "created_at", "-created_at",
]  # fmt: skip
ItemSort = Literal[
    "product_ref", "-product_ref",
    "product_name", "-product_name",
    "sku", "-sku",
    "quantity", "-quantity",
    "unit_price", "-unit_price",
    "line_total", "-line_total",
    "created_at", "-created_at",
]  # fmt: skip
OrderSort = Literal[
    "order_number", "-order_number",
    "customer_email", "-customer_email",
    "shipping_method", "-shipping_method",
    "payment_method", "-payment_method",
    "status", "-status",
    "placed_at", "-placed_at",
    "paid_at", "-paid_at",
    "completed_at", "-completed_at",
    "total_amount", "-total_amount",
    "created_at", "-created_at",
]  # fmt: skip


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
    ]


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise ValueError(str(EMAIL_INVALID)) from None
    return value


Email = Annotated[_text(EMAIL_MAX_LENGTH), AfterValidator(_email)]
SessionCode = _text(SESSION_MAX_LENGTH, 1)
Said = _text(NAME_MAX_LENGTH, 1)
Quantity = Annotated[Decimal, Field(max_digits=15, decimal_places=3, le=MAX_QUANTITY)]
Money = Annotated[int, Field(ge=0, le=MAX_AMOUNT)]
FreeValue = Annotated[str, StringConstraints(max_length=FREE_VALUE_MAX_LENGTH)]
FreeFields = Annotated[dict[str, FreeValue], Field(max_length=MAX_FREE_FIELDS)]


def _currency(value: str | None) -> str | None:
    code = (value or "").strip().upper()
    if not code:
        return None
    if len(code) != 3 or pycountry.currencies.get(alpha_3=code) is None:
        raise ValueError(str(CURRENCY_UNKNOWN))
    return code


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(50, ge=1, le=100, description="How many rows to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many rows to skip, to read the next pages.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


# ── Carts ───────────────────────────────────────────────────────────────────────────────────────


class CartRefIn(In):
    cart_id: UUID | None = Field(None, description="The cart's id.")
    session_token: SessionCode | None = Field(
        None, description="The cart's session code (e.g. sess_a1b2c3), when its id is not known."
    )
    customer: Said | None = Field(
        None,
        description="The cart's customer, when neither its id nor its code is known: their exact email "
        "or part of their name (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _said(self):
        if self.cart_id is None and self.session_token is None and self.customer is None:
            raise ValueError(str(SAY_WHICH_CART))
        return self


class CartIn(In):
    session_token: SessionCode = Field(
        description="The code that tells this visit apart (e.g. sess_a1b2c3), unique among the carts."
    )
    customer_email: Email = Field("", description="The customer's email; may be empty.")
    customer_name: _text(NAME_MAX_LENGTH) = Field("", description="The customer's name; may be empty.")
    currency: str | None = Field(
        None,
        max_length=8,
        description="ISO 4217 code (e.g. EUR). Leave it out unless the customer asked for another one: "
        "the cart then takes the business's currency.",
    )
    expires_at: dt.datetime | None = Field(
        None,
        description="When the cart expires (ISO 8601; without an offset, the business's time); empty: never.",
    )

    @field_validator("currency")
    @classmethod
    def _code(cls, value: str | None) -> str | None:
        return _currency(value)

    @field_validator("expires_at")
    @classmethod
    def _future(cls, value: dt.datetime | None) -> dt.datetime | None:
        if value is None:
            return None
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        if value <= timezone.now():
            raise ValueError(str(EXPIRY_PASSED))
        return value


class AbandonIn(CartRefIn):
    reason: _text(REASON_MAX_LENGTH) = Field(
        "", description="Why the customer did not finish, if known; it stays on the cart."
    )


class CleanupIn(In):
    """No parameters: the time is the Hub's."""


class CleanupOut(Schema):
    expired: int = Field(description="How many carts were marked as expired now.")


class CartListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Part of the session code, the customer's email or name."
    )
    session_token: str | None = Field(None, max_length=200, description="Part of the session code.")
    customer_email: str | None = Field(None, max_length=200, description="Part of the customer's email.")
    customer_name: str | None = Field(None, max_length=200, description="Part of the customer's name.")
    status: CartStatus | None = Field(
        None,
        description="Only this status: active, abandoned, converted or expired (an active cart past its "
        "expiry counts as expired).",
    )
    currency: str | None = Field(None, max_length=3, description="Only this currency (ISO 4217, e.g. EUR).")
    notes: str | None = Field(None, max_length=200, description="Part of the notes.")
    total_items_min: Decimal | None = Field(None, ge=0, description="Fewest items (sum of the quantities).")
    total_items_max: Decimal | None = Field(None, ge=0, description="Most items (sum of the quantities).")
    total_amount_min: int | None = Field(None, ge=0, description="Lowest total, in minor units of the business's currency (1250 is 12.50 with two decimals).")
    total_amount_max: int | None = Field(None, ge=0, description="Highest total, in minor units of the business's currency (1250 is 12.50 with two decimals).")
    expires_from: dt.datetime | None = Field(None, description="Expiring at this moment or later.")
    expires_to: dt.datetime | None = Field(None, description="Expiring at this moment or earlier.")
    last_activity_from: dt.datetime | None = Field(None, description="Last changed at this moment or later.")
    last_activity_to: dt.datetime | None = Field(None, description="Last changed at this moment or earlier.")
    created_from: dt.datetime | None = Field(None, description="Created at this moment or later.")
    created_to: dt.datetime | None = Field(None, description="Created at this moment or earlier.")
    sort: CartSort = Field(
        "-created_at", description="Order; a leading '-' reverses it. By default, the newest first."
    )


class CartOut(Schema):
    id: UUID = Field(description="The cart's id.")
    session_token: str = Field(description="Its session code.")
    customer_email: str = Field(description="Its customer's email; may be empty.")
    customer_name: str = Field(description="Its customer's name; may be empty.")
    status: CartStatus = Field(description="Where it is; an active cart past its expiry reads as expired.")
    total_items: Decimal = Field(description="The sum of its lines' quantities.")
    total_amount: int = Field(description="The sum of its lines' totals, in minor units of its currency.")
    currency: str = Field(description="Its currency (ISO 4217), kept from its creation: never rewritten.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    expires_at: dt.datetime | None = Field(description="When it expires; empty: never.")
    last_activity_at: dt.datetime | None = Field(description="When its lines last changed.")
    notes: str = Field(description="Its notes.")
    abandon_reason: str = Field(description="Why it was abandoned; empty unless abandoned with a reason.")
    created_by: str = Field(description="Who created it.")
    updated_by: str = Field(description="Who changed it last.")
    created_at: dt.datetime = Field(description="When it was created.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class CartPage(Page[CartOut]):
    pass


# ── Lines ───────────────────────────────────────────────────────────────────────────────────────


class ItemOut(Schema):
    id: UUID = Field(description="The line's id.")
    cart_id: UUID = Field(description="The id of its cart.")
    product_ref: str = Field(description="The product's reference, as the caller gave it.")
    product_name: str = Field(description="The product's name, as the caller gave it.")
    sku: str = Field(description="Its SKU; may be empty.")
    quantity: Decimal = Field(description="How many units.")
    unit_price: int = Field(description="The price of one unit, in minor units of the cart's currency.")
    line_total: int = Field(description="Quantity × price, rounded to the minor unit (half up).")
    variant_attributes: dict[str, Any] = Field(description="Its variant (size, colour…).")
    created_at: dt.datetime = Field(description="When it was added.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class ItemPage(Page[ItemOut]):
    pass


class CartDetailOut(CartOut):
    items: list[ItemOut] = Field(description="Its lines, in the order they were added.")


class ItemRefIn(In):
    item_id: UUID = Field(description="The line's id.")


class ItemAddIn(CartRefIn):
    product_ref: Said = Field(description="The product's reference (free text, not checked against a catalog).")
    product_name: Said = Field(description="The product's name (free text).")
    sku: _text(SKU_MAX_LENGTH) = Field("", description="The product's SKU, if any.")
    quantity: Quantity = Field(
        description="How many units, above 0 and at most 1 000 000, up to three decimals (0.5 is half a unit)."
    )
    unit_price: Money = Field(
        description="The price of one unit in minor units of the cart's currency (as many as its currency_decimals: "
        "12.50 is 1250 with two, ¥1,250 is 1250), never "
        "negative; the caller says it."
    )
    variant_attributes: FreeFields = Field(
        default_factory=dict, description="The product's variant as free fields (e.g. {\"size\": \"M\"})."
    )

    @field_validator("quantity")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError(str(QUANTITY_NOT_POSITIVE))
        return value


class ItemUpdateIn(ItemRefIn):
    quantity: Quantity = Field(
        ge=0, description="The new quantity, at most 1 000 000, up to three decimals; 0 removes the line."
    )


class ItemChangeOut(Schema):
    item: ItemOut | None = Field(description="The line as it is now; empty when it was removed.")
    removed: bool = Field(description="Whether the line was removed.")
    cart: CartOut = Field(description="Its cart, with the totals recomputed.")


class ItemListIn(PageIn):
    cart_id: UUID | None = Field(None, description="The id of the cart whose lines to list.")
    session_token: SessionCode | None = Field(
        None, description="The session code of the cart whose lines to list, when its id is not known."
    )
    search: str | None = Field(None, max_length=200, description="Part of the reference, the name or the SKU.")
    product_ref: str | None = Field(None, max_length=NAME_MAX_LENGTH, description="Only this product reference (whole).")
    product_name: str | None = Field(None, max_length=200, description="Part of the product's name.")
    sku: str | None = Field(None, max_length=200, description="Part of the SKU.")
    quantity_min: Decimal | None = Field(None, ge=0, description="Lowest quantity.")
    quantity_max: Decimal | None = Field(None, ge=0, description="Highest quantity.")
    unit_price_min: int | None = Field(None, ge=0, description="Lowest unit price, in minor units.")
    unit_price_max: int | None = Field(None, ge=0, description="Highest unit price, in minor units.")
    line_total_min: int | None = Field(None, ge=0, description="Lowest line total, in minor units.")
    line_total_max: int | None = Field(None, ge=0, description="Highest line total, in minor units.")
    sort: ItemSort = Field("created_at", description="Order; a leading '-' reverses it. By default, as added.")

    @model_validator(mode="after")
    def _said(self):
        if self.cart_id is None and self.session_token is None:
            raise ValueError(str(SAY_WHICH_CART))
        return self


# ── Orders ──────────────────────────────────────────────────────────────────────────────────────


class OrderRefIn(In):
    order_id: UUID | None = Field(None, description="The order's id.")
    order_number: Said | None = Field(
        None, description="The order's number (e.g. OS-20261014-0003), when its id is not known."
    )

    @field_validator("order_number")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _said(self):
        if self.order_id is None and self.order_number is None:
            raise ValueError(str(SAY_WHICH_ORDER))
        return self


class FailIn(OrderRefIn):
    reason: Annotated[str, StringConstraints(max_length=REASON_MAX_LENGTH)] = Field(
        description="Why the payment failed; required, it stays on the order."
    )

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(str(REASON_REQUIRED))
        return value.strip()


class CheckoutIn(CartRefIn):
    customer_email: Email | None = Field(
        None, description="The customer's email for the order; without it, the cart's."
    )
    shipping_address: FreeFields = Field(
        default_factory=dict,
        description="Where to ship, as free fields (e.g. line1, city, postal_code, country); may be empty.",
    )
    billing_address: FreeFields | None = Field(
        None, description="Where to bill, as free fields; without it, the shipping address."
    )
    shipping_method: _text(METHOD_MAX_LENGTH) = Field("", description="How it is shipped (free text).")
    payment_method: _text(METHOD_MAX_LENGTH) = Field(
        "", description="How the customer pays (free text, e.g. «card», «transfer»); nothing is charged."
    )
    notes: _text(NOTES_MAX_LENGTH) = Field("", description="Notes of the order; may be empty.")


class OrderListIn(PageIn):
    search: str | None = Field(None, max_length=200, description="Part of the order number or the email.")
    cart_id: UUID | None = Field(None, description="Only the orders of this cart.")
    order_number: str | None = Field(None, max_length=200, description="Part of the order number.")
    customer_email: str | None = Field(None, max_length=200, description="Part of the customer's email.")
    shipping_method: str | None = Field(None, max_length=METHOD_MAX_LENGTH, description="Only this shipping method (whole).")
    payment_method: str | None = Field(None, max_length=200, description="Part of the payment method.")
    status: OrderStatus | None = Field(
        None, description="Only this status: initiated, paid, failed or completed."
    )
    currency: str | None = Field(None, max_length=3, description="Only this currency (ISO 4217, e.g. EUR).")
    notes: str | None = Field(None, max_length=200, description="Part of the notes.")
    total_amount_min: int | None = Field(None, ge=0, description="Lowest total, in minor units of the business's currency (1250 is 12.50 with two decimals).")
    total_amount_max: int | None = Field(None, ge=0, description="Highest total, in minor units of the business's currency (1250 is 12.50 with two decimals).")
    placed_from: dt.datetime | None = Field(None, description="Initiated at this moment or later.")
    placed_to: dt.datetime | None = Field(None, description="Initiated at this moment or earlier.")
    paid_from: dt.datetime | None = Field(None, description="Marked as paid at this moment or later.")
    paid_to: dt.datetime | None = Field(None, description="Marked as paid at this moment or earlier.")
    completed_from: dt.datetime | None = Field(None, description="Completed at this moment or later.")
    completed_to: dt.datetime | None = Field(None, description="Completed at this moment or earlier.")
    created_from: dt.datetime | None = Field(None, description="Created at this moment or later.")
    created_to: dt.datetime | None = Field(None, description="Created at this moment or earlier.")
    sort: OrderSort = Field(
        "-created_at", description="Order; a leading '-' reverses it. By default, the newest first."
    )


class OrderOut(Schema):
    id: UUID = Field(description="The order's id.")
    cart_id: UUID = Field(description="The id of the cart it was made from.")
    session_token: str = Field(description="The session code of that cart.")
    order_number: str = Field(description="Its number, OS-YYYYMMDD-NNNN.")
    customer_email: str = Field(description="Its customer's email.")
    shipping_address: dict[str, Any] = Field(description="Where to ship (free fields).")
    billing_address: dict[str, Any] = Field(description="Where to bill (free fields).")
    shipping_method: str = Field(description="How it is shipped; may be empty.")
    payment_method: str = Field(description="How the customer pays; may be empty.")
    status: OrderStatus = Field(description="Where it is: initiated, paid, failed or completed.")
    total_amount: int = Field(description="The cart's total when it was initiated, in minor units of its currency.")
    currency: str = Field(description="Its currency (ISO 4217): its cart's, never rewritten.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    notes: str = Field(description="Its notes.")
    failure_reason: str = Field(description="Why it failed; empty unless failed.")
    placed_at: dt.datetime | None = Field(description="When it was initiated.")
    paid_at: dt.datetime | None = Field(description="When it was marked as paid.")
    failed_at: dt.datetime | None = Field(description="When it was marked as failed.")
    completed_at: dt.datetime | None = Field(description="When it was completed.")
    created_by: str = Field(description="Who initiated it.")
    updated_by: str = Field(description="Who changed it last.")
    created_at: dt.datetime = Field(description="When it was created.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class OrderPage(Page[OrderOut]):
    pass


# ── Personal data ───────────────────────────────────────────────────────────────────────────────


class CustomerEraseIn(In):
    email: Annotated[_text(EMAIL_MAX_LENGTH, 1), AfterValidator(_email)] = Field(
        description="The customer's exact email (any case): every cart and order with it loses its personal data."
    )


class CustomerEraseOut(Schema):
    carts: int = Field(description="How many carts lost the customer's personal data (deleted ones too).")
    orders: int = Field(description="How many orders lost the customer's personal data.")
