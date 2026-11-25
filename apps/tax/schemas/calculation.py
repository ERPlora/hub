"""The calculation of the tax of an amount (TAX-F18)."""

import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.tax.schemas.fields import OPERATION_CLASS, TAX_TYPE, OperationClass
from apps.tax.schemas.jurisdiction import COUNTRY, REGION, OptionalCountry, OptionalRegion, _RegionOfTheCountry
from apps.tax.schemas.references import CATEGORY_REF, CategoryRef

#: Bounds of an amount in cents (± 10 000 million euros): far beyond any sale, and exact in Decimal.
MAX_AMOUNT = 10**12


class CalculateIn(_RegionOfTheCountry, Schema):
    """An amount in cents of a category; ``date`` defaults to the business's today."""

    amount: int = Field(
        ge=-MAX_AMOUNT,
        le=MAX_AMOUNT,
        description="The amount in whole cents (10000 = 100.00).",
        json_schema_extra={"money": True},
    )
    tax_category_key: CategoryRef = Field(description=CATEGORY_REF)
    country_code: OptionalCountry = Field(
        None,
        description=COUNTRY + " Empty = the business's country and region (a region may have a tax of its own, "
        "as IGIC in the Canary Islands); naming one asks for that country alone, with the region given.",
    )
    region_code: OptionalRegion = Field(
        None, description=REGION + " Empty with no country = the business's."
    )
    date: dt.date | None = Field(
        None, description="The day of the operation; empty = the business's today."
    )
    tax_included: bool = Field(
        False, description="True if the amount already includes the tax."
    )
    allow_missing_rate: bool = Field(
        False,
        description="True to get 0 % when no rule applies; otherwise that is an error, never a guess.",
    )


class ComponentOut(Schema):
    rule_id: UUID = Field(
        description="The rule of this component (the root, or one of its components)."
    )
    label: str = Field(description="Its label, or its tax type.")
    tax_type: str = Field(description=TAX_TYPE)
    rate_pct: Decimal = Field(description="Its rate in %.")
    base: int = Field(description="The base, in cents.", json_schema_extra={"money": True})
    tax: int = Field(description="Its quota, in cents.", json_schema_extra={"money": True})


class CalculationOut(Schema):
    """Money in whole cents; the rest is the snapshot a sale line freezes, and the qualification."""

    base: int = Field(description="The base, in cents.", json_schema_extra={"money": True})
    tax: int = Field(description="The tax, in cents.", json_schema_extra={"money": True})
    total: int = Field(description="Base plus tax, in cents.", json_schema_extra={"money": True})
    tax_category_key: str = Field(description="The key of the category.")
    tax_rate_pct: Decimal = Field(description="The combined rate in %.")
    tax_country_code: str = Field(description=COUNTRY)
    tax_region_code: str | None = Field(description=REGION)
    tax_rule_id: UUID | None = Field(
        description="The root rule applied; empty when 0 % was allowed."
    )
    tax_kind: str = Field(description="The tax family declared (the root's).")
    tax_operation_class: OperationClass = Field(description=OPERATION_CLASS)
    tax_regime_key: str = Field(description="The regime code (01 = general).")
    tax_exempt_reason: str = Field(
        description="The exemption cause, on an exempt operation."
    )
    tax_included: bool = Field(description="Whether the amount included the tax.")
    source: Literal["rule", "fallback_zero"] = Field(
        description="rule, or fallback_zero when 0 % was allowed."
    )
    date: dt.date = Field(description="The day the rule was resolved for.")
    components: list[ComponentOut] = Field(
        description="One entry per component: the root, then its components."
    )
