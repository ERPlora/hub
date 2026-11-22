"""Schemas of the sessions of the till (SERVICE-F22–F27)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.service.schemas.fields import (
    A_CHECK_LINE,
    A_CUSTOMER,
    A_GRANT,
    A_RETURN,
    A_SALE,
    A_SERVICE,
    A_SESSION,
    VOUCHER_SESSION,
    VOUCHER_SESSIONS,
    In,
    Note,
)

SessionStatus = Literal["held", "consumed", "released", "expired", "returned"]


class HoldIn(In):
    grant_id: UUID = Field(description="The voucher sold whose session pays the line.", json_schema_extra=A_GRANT)
    service_id: UUID = Field(
        description="The service of the line; the voucher must cover it.", json_schema_extra=A_SERVICE
    )
    order_line_id: UUID = Field(
        description="The line of the open check (Sales) the session pays: one session per line.",
        json_schema_extra=A_CHECK_LINE,
    )


class SessionRefIn(In):
    id: UUID = Field(title=VOUCHER_SESSION, description="The session of the voucher.", json_schema_extra=A_SESSION)


class SettleIn(In):
    ids: list[Annotated[UUID, Field(json_schema_extra=A_SESSION)]] = Field(
        min_length=1,
        max_length=100,
        title=VOUCHER_SESSIONS,
        description="The sessions held for the lines the sale charges.",
    )
    sale_id: UUID = Field(description="The sale charged (Sales).", json_schema_extra=A_SALE)
    customer_id: UUID | None = Field(
        description="The sale's customer: it must own the vouchers.", json_schema_extra=A_CUSTOMER
    )


class ReturnIn(In):
    ids: list[Annotated[UUID, Field(json_schema_extra=A_SESSION)]] = Field(
        min_length=1,
        max_length=100,
        title=VOUCHER_SESSIONS,
        description="The sessions spent in the sale that come back.",
    )
    reference: UUID = Field(
        title=gettext_noop("Refund or void"),
        description="The refund, or the sale voided, that gives them back (Sales).",
        json_schema_extra=A_RETURN,
    )
    reason: Note = Field("", description="Why, as the refund or the void says it.")


class SessionOut(Schema):
    id: UUID
    grant_id: UUID
    package_id: UUID
    package_name: str
    customer_id: UUID
    service_id: UUID | None
    status: SessionStatus
    order_line_id: UUID | None
    hold_until: datetime | None
    sale_id: UUID | None
    remaining: int | None = Field(
        description="Sessions the voucher has left now; null = unlimited."
    )
    voucher_expired: bool = Field(description="The voucher is past its expiry.")
    value: int | None = Field(
        description="What the session is worth, VAT included, in cents (minor units of the business's currency): "
        "what is left of the voucher's price ÷ the sessions it has left, fixed when delivered; null until then and "
        "on an unlimited voucher.", json_schema_extra={"money": True}
    )


class SessionDetailOut(SessionOut):
    label: str = Field(
        description="How a person tells it apart: the package, its owner if the reader may see customers and the "
        "service, «5 haircuts · Lucía Pérez · Haircut»."
    )


class SessionsOut(Schema):
    rows: list[SessionOut]


class ExpiredOut(Schema):
    expired: int = Field(description="How many holds past their deadline were marked.")
