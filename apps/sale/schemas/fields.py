"""The types, limits, messages and record marks the schemas of Sales share, and their pages and closed inputs."""

from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from base.schemas.assistant import names


T = TypeVar("T")

#: Ninety-nine billion euros in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Lines of one check, legs of one charge, lines of one refund.
MAX_LINES = 200
MAX_PAYMENTS = 10
#: Options of Modifiers one line may carry (Modifiers' own ceiling, ``modifier.schemas.MAX_PICKS``).
MAX_OPTIONS = 100

SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")
SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")
SAY_WHICH_MENU = _("Say which menu: its id, or its name.")
SAY_WHICH_DISH = _("Say which dish: the choice's id, or its product's SKU or name.")
SAY_WHICH_DEPARTMENT = _(
    "Say which section (or tax category) the open price is charged at."
)
SAY_WHICH_SALE = _("Say which sale: its id or its number.")
SAY_WHICH_METHOD = _("Say which payment method: its id, its name or its type.")
SAY_WHICH_DEPARTMENT_ROW = _("Say which section: its id or its name.")
SAY_WHICH_QUICK_NOTE = _("Say which quick note: its id or its text.")
ONE_SOURCE = _(
    "Charge an open check (order_id) or loose lines (lines, service lines or open-price lines), one of the two."
)
CHECK_DISCOUNT_ON_THE_CHECK = _(
    "The discount of an open check is set on the check itself, not at the charge."
)
COUNTRY_CODE = _("Enter the country's ISO code, e.g. ES, FR or GB.")
ONE_RECORD = _("Say one record, by its id.")

# How the Sales screens name the data the models do not (the assistant's card names each datum by its title).
LINE = gettext_noop("Line")
OPEN_LINES = gettext_noop("Open-price lines")
SERVICE_LINES = gettext_noop("Services")
COMBO_LINES = gettext_noop("Menus")
# A counter sale's fixed ticket discount, named as an open check's (its model's name is the sale's total, «Discounts»).
FIXED_DISCOUNT = gettext_noop("Fixed-amount discount")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a sale by its number, a customer by their card, and the rest by ``sale.record.get``, the one
# door to what Sales names itself and to the apps it does not require (``base.E009`` lets a mark name only its own or
# a required app's read).
A_SALE = names("sale.sale.get", by="sale_id", name=("number",))
A_CUSTOMER = names("customer.customer.detail")
A_DEPARTMENT = names("sale.record.get", by="department_id")
A_QUICK_NOTE = names("sale.record.get", by="quick_note_id")
A_METHOD = names("sale.record.get", by="method_id")
A_CHECK = names("sale.record.get", by="order_id")
A_CHECK_LINE = names("sale.record.get", by="line_id")
A_SALE_LINE = names("sale.record.get", by="sale_line_id")
A_TENDER = names("sale.record.get", by="payment_id")
A_PRODUCT = names("sale.record.get", by="product_id")
#: A product said in words is found as the write finds it; the card says the words when several fit or none does.
A_PRODUCT_SAID = names("sale.record.get", by="product", as_said=True, unless=("product_id",))
A_SERVICE = names("sale.record.get", by="service_id")
A_MENU = names("sale.record.get", by="combo_id")
A_DISH = names("sale.record.get", by="dish_id")
A_MODIFIER = names("sale.record.get", by="modifier_id")
A_MEMBER = names("sale.record.get", by="staff_id")
A_BOOKING = names("sale.record.get", by="appointment_id")
A_VOUCHER = names("sale.record.get", by="grant_id")
#: One of the lines of a check a write takes, by its id, and one of the options of Modifiers a line carries.
CheckLineId = Annotated[UUID, Field(json_schema_extra=A_CHECK_LINE)]
ModifierId = Annotated[UUID, Field(json_schema_extra=A_MODIFIER)]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Said = _text(200, 1)
Label = _text(120)
Note = _text(255)
Reason = _text(500, 1)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, json_schema_extra={"money": True})]
PositiveCents = Annotated[int, Field(ge=1, le=MAX_CENTS, json_schema_extra={"money": True})]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=3)]
#: A quantity typed for a line, with as many decimals as typed: the step of the line's unit judges it and says
#: which step it is; no step is finer than three decimals, so what is kept still fits ``Quantity``.
TypedQuantity = Annotated[Decimal, Field(gt=0, lt=Decimal(10) ** 12)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
AttemptKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    ),
    Field(json_schema_extra={"attempt_key": True}),
]
DocumentType = Literal["ticket", "invoice"]
MethodType = Literal["cash", "card", "transfer", "other"]
SaleStatus = Literal["completed", "voided", "refunded"]
OrderStatus = Literal["open", "completed", "voided"]
#: AEAT's IDType of a foreign customer: 02 EU VAT, 03 passport, 04 foreign tax id, 05 residence
#: certificate, 06 other, 07 not registered; empty for a Spanish one.
IdType = Literal["", "02", "03", "04", "05", "06", "07"]
SortDir = Literal["asc", "desc"]


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


class Closed(Schema):
    """An input that refuses fields it does not know (a typo is a 422, never silently ignored)."""

    model_config = ConfigDict(extra="forbid")


class EmptyIn(Closed):
    pass
