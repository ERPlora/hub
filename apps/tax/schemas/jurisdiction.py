"""Where a tax applies: a country, a region of it, and the tax each territory declares its sales with.

The jurisdiction comes from ``pycountry`` (ISO 3166-1 and 3166-2, Debian's iso-codes): a country or a
region no business can hold would give a rule that never matches anything, and the owner would read
it on the screen believing the tax was set.
"""

from typing import Annotated, Any, Literal

import pycountry
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from pydantic import AfterValidator, BeforeValidator, ValidationInfo, field_validator

from apps.tax.choices import COUNTRY_CODES
from apps.tax.models import TaxRule
from apps.tax.schemas.fields import _blank_to_none

#: The tax family of each region with taxes of its own (TAX-F11): the Canary Islands charge IGIC, Ceuta and
#: Melilla IPSI; any other place, its country's VAT. What a line with no category or rule is declared with.
REGION_TAX_KINDS: dict[str, str] = {
    "ES-CN": TaxRule.TaxType.IGIC,
    "ES-CE": TaxRule.TaxType.IPSI,
    "ES-ML": TaxRule.TaxType.IPSI,
}
#: The tax a territory declares its sales with (TAX-F11): its country's VAT, or a region's own tax.
TerritoryTaxKind = Literal["vat", "igic", "ipsi"]
#: The short name of each territory's tax, as a message names it («Its IGIC is missing»); the long ones,
#: «IGIC (Canary Islands)», are ``TaxRule.TaxType``'s labels.
TAX_KIND_NAMES: dict[str, Promise] = {
    TaxRule.TaxType.VAT: _("VAT"),
    TaxRule.TaxType.IGIC: _("IGIC"),
    TaxRule.TaxType.IPSI: _("IPSI"),
}
#: The regions of a country with taxes of their own, which a business may keep as its own (TAX-F11).
TAX_REGIONS: dict[str, tuple[str, ...]] = {"ES": tuple(REGION_TAX_KINDS)}

REGION_UNKNOWN = _("Enter an ISO 3166-2 region, such as ES-CN.")
REGION_OF_ANOTHER_COUNTRY = _("This region does not belong to the chosen country.")


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _iso_region(value: str) -> str:
    if pycountry.subdivisions.get(code=value) is None:
        raise ValueError(str(REGION_UNKNOWN))
    return value


CountryCode = Annotated[Literal[*COUNTRY_CODES], BeforeValidator(_upper)]
OptionalCountry = Annotated[CountryCode | None, BeforeValidator(_blank_to_none)]
RegionCode = Annotated[str, AfterValidator(_iso_region), BeforeValidator(_upper)]
OptionalRegion = Annotated[RegionCode | None, BeforeValidator(_blank_to_none)]

COUNTRY = "Country, ISO 3166-1 alpha-2 (ES, PT…)."
REGION = "Region inside the country, ISO 3166-2 (ES-CN Canary Islands, ES-CE Ceuta, ES-ML Melilla); empty = the whole country."


class _RegionOfTheCountry:
    """A region names its country (``ES-CN``): one of another country would never match."""

    @field_validator("region_code", check_fields=False)
    @classmethod
    def _region_of_the_country(
        cls, region: str | None, info: ValidationInfo
    ) -> str | None:
        country = info.data.get("country_code")
        if region and country and not region.startswith(f"{country}-"):
            raise ValueError(str(REGION_OF_ANOTHER_COUNTRY))
        return region
