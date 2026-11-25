"""The tax rules: the rate of a category in a country or a region, and its components."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.tax.models import CATEGORY_KEY_MAX_LENGTH
from apps.tax.schemas.fields import (
    DIRECTION,
    OPERATION_CLASS,
    SEARCH,
    TAX_TYPE,
    Direction,
    OperationClass,
    Page,
    PageIn,
    TaxType,
    _blank_to_none,
)
from apps.tax.schemas.jurisdiction import (
    COUNTRY,
    REGION,
    CountryCode,
    OptionalCountry,
    OptionalRegion,
    _RegionOfTheCountry,
)
from apps.tax.schemas.references import A_RULE, A_TAX_CATEGORY, CATEGORY, CATEGORY_REF, T_RULE, CategoryRef

#: The countries the factory catalogue brings rules for (TAX-F16, migration 0002): Spain, and no other. A business of
#: another country has them in its database too, but they never apply to it: it creates its own in Rules (hub#996);
#: no rate of another country is planted without a reviewed source, since a made-up one would be declared.
FACTORY_COUNTRIES: frozenset[str] = frozenset({"ES"})

RATE_WITHOUT_TAX = _("This operation charges no tax: its rate must be 0 %.")
RANGE_BACKWARDS = _("The last day cannot be before the first one.")
WHICH_RULE = _("Say which rule: its id, or its country and its category.")

Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, max_length=10)
]
OptionalCode = Annotated[Code | None, BeforeValidator(_blank_to_none)]
ComponentLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=120)
]
OptionalComponentLabel = Annotated[
    ComponentLabel | None, BeforeValidator(_blank_to_none)
]


class RuleListIn(PageIn):
    """Active rules by default; ``region_code`` narrows by fragment, the other filters match whole."""

    search: str | None = Field(
        None,
        max_length=120,
        description=SEARCH + " Category, country, region or qualification.",
    )
    country_code: OptionalCountry = Field(None, description=COUNTRY)
    region_code: str | None = Field(
        None, max_length=6, description="Part of the region (CN)."
    )
    tax_category_key: str | None = Field(
        None,
        max_length=CATEGORY_KEY_MAX_LENGTH,
        description="The key of the category, whole.",
    )
    tax_type: TaxType | None = Field(None, description=TAX_TYPE)
    operation_class: OperationClass | None = Field(None, description=OPERATION_CLASS)
    regime_key: str | None = Field(
        None, max_length=10, description="The regime code, whole (01)."
    )
    parent_id: UUID | None = Field(
        None, description="Only the components of this root rule."
    )
    rate_min: Decimal | None = Field(
        None, ge=0, le=100, description="Lowest rate, in %."
    )
    rate_max: Decimal | None = Field(
        None, ge=0, le=100, description="Highest rate, in %."
    )
    status: Literal["active", "inactive", "all"] = Field(
        "active", description="active (the default), inactive (deactivated) or all."
    )
    sort: Literal[
        "tax_category_key",
        "country_code",
        "region_code",
        "rate_pct",
        "tax_type",
        "valid_from",
        "valid_to",
        "is_active",
        "operation_class",
        "regime_key",
        "id",
    ] = Field(
        "tax_category_key",
        description="Column to sort by; by category, a component follows its root.",
    )
    dir: Direction = Field("asc", description=DIRECTION)


class RuleParentIn(_RegionOfTheCountry, PageIn):
    """The slot of a new component: the roots it may hang from are the server's to say."""

    country_code: CountryCode = Field(description=COUNTRY)
    region_code: OptionalRegion = Field(None, description=REGION)
    tax_category_key: CategoryRef = Field(description=CATEGORY_REF)
    rate_pct: Rate | None = Field(
        None,
        description="The component's rate in %: at 0 a root that charges no tax takes it too.",
    )


class RuleCountriesIn(Schema):
    status: Literal["active", "inactive", "all"] = Field(
        "all", description="Rules counted: active, inactive (deactivated) or all (the default)."
    )


class RuleStatusIn(Schema):
    country_code: OptionalCountry = Field(
        None, description=COUNTRY + " Empty: the business's own, the one erplora.com registered (Spain without one)."
    )


class RuleFields(_RegionOfTheCountry, Schema):
    """A root rule; the order matters, each check reads the fields declared before it."""

    country_code: CountryCode = Field(description=COUNTRY)
    region_code: OptionalRegion = Field(None, description=REGION)
    tax_category_key: CategoryRef = Field(title=CATEGORY, description=CATEGORY_REF, json_schema_extra=A_TAX_CATEGORY)
    operation_class: OperationClass = Field("subject", description=OPERATION_CLASS)
    rate_pct: Rate = Field(
        description="The rate in %, 0 to 100, two decimals; 0 for a class that charges no tax."
    )
    tax_type: TaxType | None = Field(
        None, description=TAX_TYPE + " Empty: the family of the rule's territory (igic in ES-CN, ipsi in ES-CE "
        "and ES-ML, vat elsewhere)."
    )
    exempt_reason: OptionalCode = Field(
        None,
        description="Exemption cause of the jurisdiction (E1…E6 in Spain), only for an exempt rule.",
    )
    regime_key: OptionalCode = Field(
        None,
        description="Regime code of the jurisdiction; empty = the general one (01).",
    )
    valid_from: dt.date | None = Field(
        None, description="First day it applies (inclusive); empty = since always."
    )
    valid_to: dt.date | None = Field(
        None, description="Last day it applies (inclusive); empty = for ever."
    )

    @field_validator("rate_pct")
    @classmethod
    def _no_rate_without_tax(cls, rate: Decimal, info: ValidationInfo) -> Decimal:
        operation_class = info.data.get("operation_class")
        if operation_class and operation_class != "subject" and rate != 0:
            raise ValueError(str(RATE_WITHOUT_TAX))
        return rate

    @field_validator("valid_to")
    @classmethod
    def _range_forwards(
        cls, valid_to: dt.date | None, info: ValidationInfo
    ) -> dt.date | None:
        valid_from = info.data.get("valid_from")
        if valid_to and valid_from and valid_to < valid_from:
            raise ValueError(str(RANGE_BACKWARDS))
        return valid_to


class RuleIn(RuleFields):
    """A rule; with ``parent_id`` it is a component (the equivalence surcharge) of that root rule."""

    parent_id: UUID | None = Field(
        None,
        description="The root rule this one is a component of (same country, region and category).",
        json_schema_extra=A_RULE,
    )
    component_label: OptionalComponentLabel = Field(
        None,
        description="How the component is named in a breakdown (Recargo de equivalencia).",
    )


class RuleBulkItem(RuleFields):
    # A field the batch does not know (a parent_id) is refused, never dropped: dropping it would
    # turn a component into a root rule.
    model_config = ConfigDict(extra="forbid")


class RuleBulkIn(Schema):
    rules: list[RuleBulkItem] = Field(
        min_length=1,
        max_length=100,
        description="1 to 100 root rules, saved all or none.",
    )


class RuleRefIn(_RegionOfTheCountry, Schema):
    """Which rule: its ``id``, or its country, region and category (by voice).

    By its slot, deactivating or ending names the active root rule in force today, and reactivating
    the most recent deactivated root rule of that slot.
    """

    id: UUID | None = Field(None, title=T_RULE, description="The rule's id.", json_schema_extra=A_RULE)
    country_code: OptionalCountry = Field(
        None, description=COUNTRY + " With the category, instead of the id."
    )
    region_code: OptionalRegion = Field(None, description=REGION)
    tax_category_key: CategoryRef | None = Field(
        None, title=CATEGORY, description=CATEGORY_REF + " With the country, instead of the id.", json_schema_extra=A_TAX_CATEGORY
    )

    @model_validator(mode="after")
    def _named(self) -> "RuleRefIn":
        if self.id is None and not (self.country_code and self.tax_category_key):
            raise ValueError(str(WHICH_RULE))
        return self


class RuleGetIn(Schema):
    id: UUID = Field(description="The rule's id.")


class RuleEndIn(RuleRefIn):
    valid_to: dt.date = Field(
        description="The last day the rule applies (inclusive): the day before the new rate starts."
    )


class RuleOut(Schema):
    id: UUID = Field(description="The rule's id.")
    country_code: str = Field(description=COUNTRY)
    region_code: str | None = Field(description=REGION)
    tax_category_key: str = Field(description="The key of its category.")
    tax_category_name: str = Field(
        description="The name of its category, in the reader's language."
    )
    rate_pct: Decimal = Field(description="The rate in %.")
    tax_type: TaxType = Field(description=TAX_TYPE)
    operation_class: OperationClass = Field(description=OPERATION_CLASS)
    exempt_reason: str | None = Field(description="Exemption cause, on an exempt rule.")
    regime_key: str | None = Field(description="Regime code; empty = the general one.")
    parent_id: UUID | None = Field(
        description="The root rule of a component; empty on a root rule."
    )
    component_label: str | None = Field(description="The label of a component.")
    valid_from: dt.date | None = Field(
        description="First day it applies; empty = since always."
    )
    valid_to: dt.date | None = Field(
        description="Last day it applies; empty = for ever."
    )
    is_active: bool = Field(
        description="Active; a deactivated rule applies to nothing new."
    )
    updated_at: dt.datetime = Field(description="Last change.")


RulePage = Page[RuleOut]


class RuleNamedOut(RuleOut):
    label: str = Field(
        description="How a person names the rule, in the reader's language: its category, a component's label, its "
        "country (and region) and its rate (Restaurant — food · Spain · 10%)."
    )


class RuleBulkOut(Schema):
    rules: list[RuleOut] = Field(description="The rules created, in the order sent.")


class RuleStatusOut(Schema):
    country_code: str = Field(description="The country counted: the one asked, or the business's.")
    matching_rules: int = Field(
        description="Active root rules in force today in that country (another country's never count)."
    )
    configured: bool = Field(
        description="True when at least one applies: the till can price a sale."
    )
    factory_rules: bool = Field(
        description="True when Taxes brings that country's rules ready (only Spain's); otherwise the business "
        "creates its own in Rules."
    )


class RuleCountriesOut(Schema):
    countries: list[str] = Field(
        description="The countries (ISO 3166-1 alpha-2) the business has rules for, once each, sorted."
    )
