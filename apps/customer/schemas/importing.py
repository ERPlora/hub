"""Schemas of importing customers from a CSV: the rows sent and what became of each."""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.customer.schemas.fields import CHANNEL, SOURCE, STAGE


class ImportRowIn(Schema):
    """One row of a CSV, as text: the service checks each row on its own."""

    name: str = Field("", max_length=1000, description="Name (required on each row).")
    email: str = Field("", max_length=1000, description="Email.")
    phone: str = Field("", max_length=1000, description="Phone as typed.")
    tax_id: str = Field("", max_length=1000, description="Tax id.")
    company_name: str = Field("", max_length=1000, description="Company.")
    address: str = Field("", max_length=1000, description="Street and number.")
    city: str = Field("", max_length=1000, description="City.")
    postal_code: str = Field("", max_length=1000, description="Postal code.")
    country: str = Field(
        "", max_length=1000, description="Country, as its two-letter code."
    )
    avatar: str = Field(
        "", max_length=1000, description="Address (URL) of the picture."
    )
    birthday: str = Field("", max_length=1000, description="Birthday, YYYY-MM-DD.")
    anniversary: str = Field(
        "", max_length=1000, description="Anniversary, YYYY-MM-DD."
    )
    lifecycle_stage: str = Field(
        "", max_length=1000, description=f"Stage; empty is active. {STAGE}"
    )
    source: str = Field(
        "", max_length=1000, description=f"Source; empty is import. {SOURCE}"
    )
    preferred_channel: str = Field("", max_length=1000, description=CHANNEL)
    notes: str = Field("", max_length=10000, description="Internal notes.")


class ImportIn(Schema):
    rows: list[ImportRowIn] = Field(
        min_length=1,
        max_length=50,
        title=gettext_noop("Rows to import"),
        description="One to fifty rows of the file.",
    )


class ImportRowOut(Schema):
    index: int = Field(description="The row's position in the block sent, from 0.")
    id: UUID | None = Field(
        description="The new customer's id; empty when the row was skipped."
    )
    errors: dict[str, str] = Field(description="Why the row was skipped, per column.")
    warnings: dict[str, str] = Field(
        description="What to review on a created row, per column."
    )


class ImportOut(Schema):
    created: int = Field(description="How many rows became customers.")
    skipped: int = Field(description="How many rows were skipped.")
    rows: list[ImportRowOut] = Field(description="The result of each row.")
