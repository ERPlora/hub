"""Input and output schemas of the tax app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).

The jurisdiction comes from ``pycountry`` (ISO 3166-1 and 3166-2, Debian's iso-codes): a country or a
region no business can hold would give a rule that never matches anything, and the owner would read
it on the screen believing the tax was set (taxes#41).

A category may be named by its key, its name or an alias wherever an existing one is referred to
(``tax_category_key`` of a rule, an alias, a calculation, a lookup): the assistant is used by voice.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.tax.models import CATEGORY_KEY_MAX_LENGTH, CATEGORY_KEY_RE, TaxAlias, TaxRule

T = TypeVar("T")

#: The 249 officially assigned ISO 3166-1 alpha-2 codes (no ZZ, EU or XK).
COUNTRY_CODES: tuple[str, ...] = tuple(
    sorted(country.alpha_2 for country in pycountry.countries)
)
#: The business's country: Spain until the Hub receives the one the business chose in its ERPlora account
#: (the SaaS's registry, phase 2), as the tax engine of the current product did.
DEFAULT_COUNTRY = "ES"
#: The regions of a country with taxes of their own, which a business may keep as its own (TAX-F11): the
#: Canary Islands charge IGIC, Ceuta and Melilla IPSI. Any other region charges its country's tax.
TAX_REGIONS: dict[str, tuple[str, ...]] = {"ES": ("ES-CN", "ES-CE", "ES-ML")}
#: Bounds of an amount in cents (± 10 000 million euros): far beyond any sale, and exact in Decimal.
MAX_AMOUNT = 10**12

REGION_UNKNOWN = _("Enter an ISO 3166-2 region, such as ES-CN.")
REGION_OF_ANOTHER_COUNTRY = _("This region does not belong to the chosen country.")
REGION_NOT_AVAILABLE = _(
    "This region has no taxes of its own in your business's country: choose one of its tax territories, or none."
)
RATE_WITHOUT_TAX = _("This operation charges no tax: its rate must be 0 %.")
RANGE_BACKWARDS = _("The last day cannot be before the first one.")
WHICH_RULE = _("Say which rule: its id, or its country and its category.")


def normalize_text(text: str) -> str:
    """How an outside text is compared: lowercase, single spaces, no spaces at the ends."""
    return " ".join(text.split()).lower()


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _normalized(value: Any) -> Any:
    return normalize_text(value) if isinstance(value, str) else value


def _iso_region(value: str) -> str:
    if pycountry.subdivisions.get(code=value) is None:
        raise ValueError(str(REGION_UNKNOWN))
    return value


CountryCode = Annotated[Literal[*COUNTRY_CODES], BeforeValidator(_upper)]
OptionalCountry = Annotated[CountryCode | None, BeforeValidator(_blank_to_none)]
RegionCode = Annotated[str, AfterValidator(_iso_region), BeforeValidator(_upper)]
OptionalRegion = Annotated[RegionCode | None, BeforeValidator(_blank_to_none)]
NewCategoryKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=CATEGORY_KEY_MAX_LENGTH,
        pattern=CATEGORY_KEY_RE,
    ),
]
#: An existing category, by its key, its name or an alias (``queries.resolve_category_text``).
CategoryRef = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
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
AliasText = Annotated[
    str, StringConstraints(min_length=1, max_length=200), BeforeValidator(_normalized)
]

TaxType = Literal[*TaxRule.TaxType.values]
OperationClass = Literal[*TaxRule.OperationClass.values]
AliasSource = Literal[*TaxAlias.Source.values]
Direction = Literal["asc", "desc"]

# Descriptions shared by several schemas.
COUNTRY = "Country, ISO 3166-1 alpha-2 (ES, PT…)."
REGION = "Region inside the country, ISO 3166-2 (ES-CN Canary Islands, ES-CE Ceuta, ES-ML Melilla); empty = the whole country."
CATEGORY_REF = "The tax category: its key (product.generic), its name (Restaurant — food) or an alias (beer)."
SEARCH = "Free text to search."
DIRECTION = "Sort direction: asc or desc."
TAX_TYPE = "Tax family: vat, igic (Canary Islands), ipsi (Ceuta and Melilla), surcharge, sales_tax, withholding, excise or import_duty."
OPERATION_CLASS = (
    "Fiscal qualification: subject, subject_reverse (reverse charge), exempt, not_subject or "
    "not_subject_location (place of supply rules). Every class but subject charges no tax."
)


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


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


# Inputs: categories


class CategoryListIn(_RegionOfTheCountry, PageIn):
    """The active categories; each row says its rate in force today where ``country_code`` and
    ``region_code`` say."""

    search: str | None = Field(
        None,
        max_length=120,
        description=SEARCH + " Key, name or description, stored or translated.",
    )
    key: str | None = Field(
        None, max_length=CATEGORY_KEY_MAX_LENGTH, description="Part of the key."
    )
    name: str | None = Field(
        None, max_length=255, description="Part of the stored name."
    )
    display_name: str | None = Field(
        None, max_length=255, description="Part of the name as the reader sees it."
    )
    display_description: str | None = Field(
        None,
        max_length=1000,
        description="Part of the description as the reader sees it.",
    )
    is_system: bool | None = Field(
        None, description="True: factory categories only; false: the business's own."
    )
    sort: Literal[
        "key",
        "name",
        "display_name",
        "display_description",
        "is_system",
        "is_active",
        "id",
    ] = Field("key", description="Column to sort by.")
    dir: Direction = Field("asc", description=DIRECTION)
    country_code: OptionalCountry = Field(
        None,
        description=COUNTRY + " Where the rate column is read; empty = the business's country and region.",
    )
    region_code: OptionalRegion = Field(None, description=REGION)


class CategoryGetIn(Schema):
    key: CategoryRef = Field(description=CATEGORY_REF)


class CategoryIn(Schema):
    key: NewCategoryKey = Field(
        description="The key products and services link to; lowercase, starting with a letter; letters, digits, "
        "dots and underscores (product.books). It never changes."
    )
    name: Name = Field(description="The name shown.")
    description: Description = Field("", description="An optional description.")
    is_system: bool = Field(
        False, description="Mark it as a factory category (shown as «System»)."
    )


# Inputs: rules


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
        None, description=COUNTRY + " The business's; empty = any country counts."
    )


class RuleFields(_RegionOfTheCountry, Schema):
    """A root rule; the order matters, each check reads the fields declared before it."""

    country_code: CountryCode = Field(description=COUNTRY)
    region_code: OptionalRegion = Field(None, description=REGION)
    tax_category_key: CategoryRef = Field(description=CATEGORY_REF)
    operation_class: OperationClass = Field("subject", description=OPERATION_CLASS)
    rate_pct: Rate = Field(
        description="The rate in %, 0 to 100, two decimals; 0 for a class that charges no tax."
    )
    tax_type: TaxType = Field("vat", description=TAX_TYPE)
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

    id: UUID | None = Field(None, description="The rule's id.")
    country_code: OptionalCountry = Field(
        None, description=COUNTRY + " With the category, instead of the id."
    )
    region_code: OptionalRegion = Field(None, description=REGION)
    tax_category_key: CategoryRef | None = Field(
        None, description=CATEGORY_REF + " With the country, instead of the id."
    )

    @model_validator(mode="after")
    def _named(self) -> "RuleRefIn":
        if self.id is None and not (self.country_code and self.tax_category_key):
            raise ValueError(str(WHICH_RULE))
        return self


class RuleEndIn(RuleRefIn):
    valid_to: dt.date = Field(
        description="The last day the rule applies (inclusive): the day before the new rate starts."
    )


# Inputs: aliases


class AliasListIn(PageIn):
    """The active aliases."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Alias or category key."
    )
    alias: str | None = Field(None, max_length=200, description="Part of the alias.")
    tax_category_key: str | None = Field(
        None,
        max_length=CATEGORY_KEY_MAX_LENGTH,
        description="The key of the category, whole.",
    )
    source: AliasSource | None = Field(
        None, description="shipped (factory) or learned."
    )
    sort: Literal["alias", "tax_category_key", "source", "is_active", "id"] = Field(
        "alias", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=DIRECTION)


class AliasResolveIn(Schema):
    text: AliasText = Field(
        description="An outside text (a CSV cell: IVA 10, beer, comida) to read as a category."
    )


class AliasIn(Schema):
    alias: AliasText = Field(
        description="The outside text; kept lowercase with single spaces."
    )
    tax_category_key: CategoryRef = Field(description=CATEGORY_REF)
    source: AliasSource = Field(
        "learned", description="learned (the default) or shipped (factory)."
    )


# Inputs: the calculation


class CalculateIn(_RegionOfTheCountry, Schema):
    """An amount in cents of a category; ``date`` defaults to the business's today."""

    amount: int = Field(
        ge=-MAX_AMOUNT,
        le=MAX_AMOUNT,
        description="The amount in whole cents (10000 = 100.00).",
    )
    tax_category_key: CategoryRef = Field(description=CATEGORY_REF)
    country_code: OptionalCountry = Field(
        None,
        description=COUNTRY + " Empty = the business's country and region (TAX-F11); naming one asks for "
        "that country alone, with the region given.",
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


# Outputs


class CategoryOut(Schema):
    id: UUID = Field(description="The category's id.")
    key: str = Field(description="The key products and services link to.")
    name: str = Field(description="The stored name (English for a factory category).")
    description: str = Field(description="The stored description.")
    display_name: str = Field(description="The name to show, in the reader's language.")
    display_description: str = Field(
        description="The description to show, in the reader's language."
    )
    is_system: bool = Field(
        description="A factory category («System»); otherwise the business's own."
    )
    is_active: bool = Field(description="Active.")


class CategoryRowOut(CategoryOut):
    rate_pct: Decimal | None = Field(
        description="The rate in force today where asked, components included; empty without a rule."
    )
    operation_class: OperationClass | None = Field(
        description="Its qualification; empty without a rule."
    )


CategoryPage = Page[CategoryRowOut]


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


class RuleBulkOut(Schema):
    rules: list[RuleOut] = Field(description="The rules created, in the order sent.")


class RuleStatusOut(Schema):
    country_code: str | None = Field(description="The country asked; empty = any.")
    matching_rules: int = Field(
        description="Active root rules in force today in that country."
    )
    configured: bool = Field(
        description="True when at least one applies: the till can price a sale."
    )


class RuleCountriesOut(Schema):
    countries: list[str] = Field(
        description="The countries (ISO 3166-1 alpha-2) the business has rules for, once each, sorted."
    )


class AliasOut(Schema):
    id: UUID = Field(description="The alias's id.")
    alias: str = Field(description="The outside text.")
    tax_category_key: str = Field(description="The key of its category.")
    tax_category_name: str = Field(
        description="The name of its category, in the reader's language."
    )
    source: AliasSource = Field(description="shipped (factory) or learned.")
    is_active: bool = Field(description="Active.")


AliasPage = Page[AliasOut]


class AliasResolveOut(Schema):
    text: str = Field(description="The text as compared (lowercase, single spaces).")
    tax_category_key: str | None = Field(
        description="The key of the category it is; empty if none."
    )
    matched_by: Literal["key", "name", "alias"] | None = Field(
        description="What matched: key, name or alias."
    )


class ComponentOut(Schema):
    rule_id: UUID = Field(
        description="The rule of this component (the root, or one of its components)."
    )
    label: str = Field(description="Its label, or its tax type.")
    tax_type: str = Field(description=TAX_TYPE)
    rate_pct: Decimal = Field(description="Its rate in %.")
    base: int = Field(description="The base, in cents.")
    tax: int = Field(description="Its quota, in cents.")


class CalculationOut(Schema):
    """Money in whole cents; the rest is the snapshot a sale line freezes, and the qualification."""

    base: int = Field(description="The base, in cents.")
    tax: int = Field(description="The tax, in cents.")
    total: int = Field(description="Base plus tax, in cents.")
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


class TaxSettingsOut(Schema):
    country_code: str = Field(description="The business's country, ISO 3166-1 alpha-2.")
    region_code: str | None = Field(
        description="The business's region (ES-CN, ES-CE, ES-ML); empty = the whole country."
    )
    regions: list[str] = Field(
        description="The regions with taxes of their own the business may keep, in its country."
    )
    updated_at: dt.datetime | None = Field(description="Last change; empty = never changed.")
