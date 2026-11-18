"""Schemas of the business's settings (``base.business.get``) and its locations (``base.location.list``)."""

from uuid import UUID

from ninja import Schema
from pydantic import Field


# ── Business settings and the hub's context ───────────────


class BusinessIn(Schema):
    """No input: the business of the hub this person is on."""


class BusinessOut(Schema):
    """``base.business.get``: the business as the SaaS registered it, each value named in the person's language."""

    name: str = Field(description="The business's name (on ERPlora's own hub, its issuer's legal name); empty in a demo.")
    country: str = Field(description="ISO 3166-1 alpha-2; empty in a demo. It no longer changes once the business is ready.")
    country_name: str
    timezone: str = Field(description="IANA time zone: the business's clock (the deployment's when it has none).")
    language: str = Field(description="The business's language: the one of whoever has not chosen their own.")
    language_name: str
    currency: str = Field(description="ISO 4217: the one the business's country pays in (the euro without a country).")
    currency_label: str = Field(description="«EUR · Euro»: the code and its name.")
    currency_decimals: int
    demo: bool = Field(description="A demo has no business on erplora.com: nothing to change there.")
    settings_url: str = Field(
        description="The business's settings on erplora.com, where an owner or an administrator changes its name, time "
        "zone and language; empty in a demo and on ERPlora's own hub."
    )



# ── Locations ──────────────────────────────────────────────────────────────────────────────────────────────────────


class LocationListIn(Schema):
    """No input."""


class LocationOut(Schema):
    id: UUID
    name: str = Field(description="Its name; the default «Main» in the reader's language while it keeps that name.")
    is_default: bool = Field(description="The place the business works in unless another one is chosen.")
    is_active: bool


class LocationListOut(Schema):
    locations: list[LocationOut] = Field(description="The default first, then by name.")

