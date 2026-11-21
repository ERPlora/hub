"""Taxes' «today» in a business of another zone is the business's: the day a rate changes starts at its own midnight,
not at the deployment's (Madrid)."""

import datetime as dt

import pytest
from django.utils import timezone
from live.operations import get

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.schemas import CalculateIn
from apps.tax.tests.conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

#: 23:30 of 2 November in Bogotá; 05:30 of the 3rd in Madrid.
NIGHT_IN_BOGOTA = dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC)


@pytest.fixture
def rate_turns_at_midnight(db):
    """A category whose rate changes at the turn of the night: 10 % until the 2nd, 21 % from the 3rd."""
    category = TaxCategory.objects.create(key="test.turn", name="Turn of the night")
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="10", valid_to=dt.date(2026, 11, 2))
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="21", valid_from=dt.date(2026, 11, 3))


def test_at_night_elsewhere_the_rate_of_today_is_the_business_s(rate_turns_at_midnight, monkeypatch, in_business_a):
    monkeypatch.setattr(timezone, "now", lambda: NIGHT_IN_BOGOTA)
    monkeypatch.setattr(in_business_a, "timezone", "America/Bogota")
    calculation = get("tax.rate.calculate")(ctx_for(), CalculateIn(amount=1000, tax_category_key="test.turn"))
    assert (calculation.tax_rate_pct, calculation.tax) == (10, 100)
