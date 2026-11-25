"""The business's jurisdiction (TAX-F11): its today, its country and the region it keeps, and the tax family of each
territory: what every calculation reads when it names no country, and what a line without a category or a rule is
declared with."""

import datetime as dt

from django.utils import timezone
from live.errors import InvalidPayload

from apps.tax.models import TaxRule, TaxSettings
from apps.tax.schemas.jurisdiction import REGION_OF_ANOTHER_COUNTRY, REGION_TAX_KINDS, TAX_REGIONS
from base import operations as platform
from base.business import business_zone, country_or_market

DEFAULT_TAX_KIND = TaxRule.TaxType.VAT


def business_today() -> dt.date:
    """The business's today, on its clock (``business_zone``), not UTC: the till sells on the local date."""
    return timezone.localdate(timezone=business_zone())


def business_jurisdiction() -> tuple[str, str | None]:
    """The business's ``(COUNTRY, REGION or None)``: the one source every calculation that names no country
    reads (sales, invoice, the API; TAX-F11). The country is the one erplora.com registered for the business at
    work, Spain without one (a demo, ERPlora's own hub), read as Customers and VeriFactu read it (hub#996): a
    country without rules of its own is refused, never charged Spain's. The region is the one it keeps in Taxes'
    settings, and only while it is one of that country's tax territories."""
    country = platform.current_business_country()
    settings = TaxSettings.objects.first()
    region = (settings.region_code or None) if settings else None
    return country, region if region in TAX_REGIONS.get(country, ()) else None


def _jurisdiction(country_code: str | None, region_code: str | None) -> tuple[str, str | None]:
    """``(COUNTRY, REGION or None)`` as the rules store them: capitals, no spaces, empty = none.

    No country is the business's jurisdiction, its region included unless one is given; naming a country
    asks for that country alone, with the region given."""
    region = (region_code or "").strip().upper() or None
    country = (country_code or "").strip().upper()
    if not country:
        country, kept = business_jurisdiction()
        region = region or kept
    return country, region


def own_tax_kind(country_code: str, region_code: str | None) -> str | None:
    """The tax of a region of ``country_code`` with one of its own (IGIC in ES-CN, IPSI in ES-CE and ES-ML), or
    ``None``: the region charges its country's VAT (a region of another country, too)."""
    kind = REGION_TAX_KINDS.get(region_code or "")
    return kind if kind and region_code.startswith(f"{country_code}-") else None


def tax_kind_of(country_code: str | None, region_code: str | None) -> str:
    """The tax family of a territory (TAX-F11): IGIC in the Canary Islands, IPSI in Ceuta and Melilla, VAT
    anywhere else. What a line with no category or rule is declared with (``Impuesto`` 03, 02 or 01)."""
    country, region = _jurisdiction(country_or_market(country_code or ""), region_code)
    return own_tax_kind(country, region) or DEFAULT_TAX_KIND


def business_tax_kind() -> str:
    """The tax family of the business's own territory (``business_jurisdiction``)."""
    return tax_kind_of(*business_jurisdiction())


def asked_jurisdiction(country_code: str | None, region_code: str | None) -> tuple[str, str | None]:
    """The jurisdiction a reader asks for, as ``_jurisdiction``; a region of another country than the one
    it falls in is a 422 on its field, never a silent national rate."""
    country, region = _jurisdiction(country_code, region_code)
    if region and not region.startswith(f"{country}-"):
        message = str(REGION_OF_ANOTHER_COUNTRY)
        raise InvalidPayload(message, fields={"region_code": message})
    return country, region
