"""Schemas of erasing a customer's personal data."""

from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.fields import CustomerRefIn, _text


class EraseIn(CustomerRefIn):
    reason: _text(500) = Field(
        "", description="Why the data is erased; kept in the audit entry."
    )


class ErasedOut(Schema):
    id: UUID = Field(
        description="The id of the customer whose personal data was erased."
    )
