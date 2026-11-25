"""The business's tax settings: its region (TAX-F11)."""

import datetime as dt

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict

from apps.tax.schemas.jurisdiction import REGION, OptionalRegion, TerritoryTaxKind

REGION_NOT_AVAILABLE = _(
    "This region has no taxes of its own in your business's country: choose one of its tax territories, or none."
)


class SettingsGetIn(Schema):
    """Nothing to say: a business has one set of tax settings."""

    model_config = ConfigDict(extra="forbid")


class TaxSettingsIn(Schema):
    """The business's region: one of its country's tax territories, or none (the whole country)."""

    model_config = ConfigDict(extra="forbid")

    region_code: OptionalRegion = Field(
        None,
        description=REGION + " One of the regions with taxes of their own of the business's country.",
    )


class TaxSettingsOut(Schema):
    country_code: str = Field(description="The business's country, ISO 3166-1 alpha-2.")
    region_code: str | None = Field(
        description="The business's region (ES-CN, ES-CE, ES-ML); empty = the whole country."
    )
    regions: list[str] = Field(
        description="The regions with taxes of their own the business may keep, in its country."
    )
    tax_kind: TerritoryTaxKind = Field(
        description="The tax the business's sales are declared with, its territory's: vat, igic (Canary Islands) "
        "or ipsi (Ceuta and Melilla). The one source every app names the tax by."
    )
    updated_at: dt.datetime | None = Field(description="Last change; empty = never changed.")
