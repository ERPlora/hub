"""The money of a tax and its calculation: whole cents, exact decimals, half up. ``calculate_tax`` is what sales and
invoice call inside their own operation, and ``tax.rate.calculate`` wraps it."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.tax.models import TaxRule
from apps.tax.queries.jurisdiction import _jurisdiction, asked_jurisdiction, business_today, tax_kind_of
from apps.tax.queries.naming import category_by_reference
from apps.tax.queries.resolution import GENERAL_REGIME, resolve_tax
from apps.tax.schemas import CalculateIn, CalculationOut

NO_RATE = _("No tax rule applies to this category in this country.")

_CENT = Decimal(1)
_HUNDRED = Decimal(100)


def round_half_up(value: Decimal) -> int:
    """To the cent, a half away from zero (52.5 → 53, -52.5 → -53)."""
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def split_amount(
    amount: int, rates: list[Decimal], *, tax_included: bool
) -> tuple[int, int, list[int]]:
    """``(base, tax, quota of each rate)`` of ``amount`` cents, one rounding per magnitude.

    Without the tax, each quota is base × rate. With it, the base is amount ÷ (1 + combined rate) and
    the tax is what remains, so the amount charged never moves a cent; the last component WITH a rate
    absorbs the rounding so that the quotas add up to the tax exactly (a component at 0 % never
    carries a quota; if every rate is 0, there is no tax to adjust).
    """
    if not tax_included:
        quotas = [round_half_up(amount * rate / _HUNDRED) for rate in rates]
        return amount, sum(quotas), quotas
    combined = sum(rates, Decimal(0))
    base = round_half_up(amount * _HUNDRED / (_HUNDRED + combined))
    tax = amount - base
    quotas = [round_half_up(base * rate / _HUNDRED) for rate in rates]
    taxed = [index for index, rate in enumerate(rates) if rate > 0]
    if taxed:
        last = taxed[-1]
        quotas[last] = tax - (sum(quotas) - quotas[last])
    return base, tax, quotas


def calculate_tax(  # noqa: PLR0913
    *,
    amount: int,
    category_key: str,
    country_code: str | None = None,
    region_code: str | None = None,
    on: dt.date | None = None,
    tax_included: bool = False,
    allow_missing_rate: bool = False,
) -> dict:
    """The tax of ``amount`` cents (a ``CalculationOut``). Without a rule: 409 ``tax.no_rate``,
    unless the caller explicitly allows 0 %. A rule that cannot be read raises: nothing is guessed."""
    on = on or business_today()
    country_code, region_code = _jurisdiction(country_code, region_code)
    resolution = resolve_tax(
        category_key=category_key,
        country_code=country_code,
        region_code=region_code,
        on=on,
    )
    if resolution is None and not allow_missing_rate:
        raise Conflict(NO_RATE, code="tax.no_rate")
    components = resolution.components if resolution else []
    base, tax, quotas = split_amount(
        amount, [rule.rate_pct for rule in components], tax_included=tax_included
    )
    return {
        "base": base,
        "tax": tax,
        "total": base + tax,
        "tax_category_key": category_key,
        "tax_rate_pct": resolution.rate_pct if resolution else Decimal(0),
        "tax_country_code": country_code,
        "tax_region_code": region_code,
        "tax_rule_id": resolution.root.id if resolution else None,
        "tax_kind": resolution.tax_kind if resolution else tax_kind_of(country_code, region_code),
        "tax_operation_class": resolution.operation_class
        if resolution
        else TaxRule.OperationClass.SUBJECT,
        "tax_regime_key": resolution.regime_key if resolution else GENERAL_REGIME,
        "tax_exempt_reason": resolution.exempt_reason if resolution else "",
        "tax_included": tax_included,
        "source": "rule" if resolution else "fallback_zero",
        "date": on,
        "components": [
            {
                "rule_id": rule.id,
                "label": rule.label,
                "tax_type": rule.tax_type,
                "rate_pct": rule.rate_pct,
                "base": base,
                "tax": quota,
            }
            for rule, quota in zip(components, quotas, strict=True)
        ],
    }


@operation(
    "tax.rate.calculate",
    kind="query",
    permission="tax.view",
    input=CalculateIn,
    output=CalculationOut,
    ai={
        "asks": {
            "en": (
                "how much VAT does a 12 euro meal carry?",
                "work out the tax of 50 euros at the reduced rate",
                "calculate base, tax and total for a 30 € book",
            ),
            "es": (
                "¿cuánto IVA lleva un menú de 15 euros?",
                "calcula el impuesto de 40 € de cerveza con el IVA incluido",
                "¿qué base y qué total salen de 100 € en la categoría de libros?",
            ),
        },
        "description": "Resolve and calculate the tax of an amount in cents for a tax category (its key, name or "
        "alias), in the business's country and region unless a country is named: base, tax, total, the rate and "
        "the fiscal qualification of the operation. Without an applicable rule it fails instead of guessing a rate."
    },
)
def calculate(ctx: OperationContext, params: CalculateIn) -> dict:
    category = category_by_reference(params.tax_category_key)
    country_code, region_code = asked_jurisdiction(params.country_code, params.region_code)
    return calculate_tax(
        amount=params.amount,
        # A text that names no category has no rule either: tax.no_rate, never a guessed one.
        category_key=category.key if category else params.tax_category_key,
        country_code=country_code,
        region_code=region_code,
        on=params.date,
        tax_included=params.tax_included,
        allow_missing_rate=params.allow_missing_rate,
    )
