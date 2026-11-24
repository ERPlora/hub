"""Schemas of the issuer, the business's tax identity: reading it, changing it and the SaaS's photo of it.
"""

import datetime as dt
from typing import Any

from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.invoice.schemas.document_issuer import IntraEuOperatorIn, IntraEuOperatorOut
from apps.invoice.schemas.fields import HOME_COUNTRY, NAME_MAX, TAX_ID_MAX, _country, _text, check_tax_id
from apps.tax.choices import COUNTRY_CODES


class IssuerGetIn(Schema):
    """The business's tax identity."""


class IssuerIn(IntraEuOperatorIn):
    legal_name: _text(NAME_MAX, min_length=1) = Field(
        description="Legal name of the business."
    )
    # Tax's closed list of countries, so the card says the country by its name («España»), never its code.
    country: str = Field(
        HOME_COUNTRY,
        description="Country of the business, ISO 3166-1 alpha-2; default ES.",
        json_schema_extra={"enum": list(COUNTRY_CODES), "choices_of": "tax.country_code"},
    )
    tax_id: _text(TAX_ID_MAX, min_length=1) = Field(
        description="Tax ID of the business (a Spanish NIF or CIF, checked)."
    )
    address: _text(255, min_length=1) = Field(description="Street and number.")
    postal_code: _text(20) = Field("", description="Postal code.")
    city: _text(100) = Field("", description="City.")
    province: _text(100) = Field("", description="Province.")

    @field_validator("country", mode="before")
    @classmethod
    def _iso_country(cls, value: Any) -> str:
        return _country(value, home_is_empty=False)

    @field_validator("tax_id")
    @classmethod
    def _valid_tax_id(cls, value: str, info: ValidationInfo) -> str:
        # The issuer's own NIF or CIF is checked; a business abroad keeps its tax ID as written.
        country = info.data.get("country", HOME_COUNTRY)
        if country != HOME_COUNTRY:
            return value.strip()
        return check_tax_id(value, country=country, id_type="")


class IssuerSyncIn(IssuerIn):
    version: int = Field(
        ge=0,
        description="Version of the SaaS's photo it comes with; an older one is ignored.",
    )


class IssuerOut(IntraEuOperatorOut):
    configured: bool
    legal_name: str
    tax_id: str
    address: str
    postal_code: str
    city: str
    province: str
    country: str
    address_line: str
    source: str
    synced_version: int | None
    synced_at: dt.datetime | None
    updated_at: dt.datetime | None


class IssuerSyncOut(Schema):
    applied: bool = Field(description="False when an older photo was ignored.")
    issuer: IssuerOut
