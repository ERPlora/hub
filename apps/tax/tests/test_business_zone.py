"""Taxes' «today» in a business of another zone is the business's: the day a rate changes starts at its own midnight,
not at the deployment's (Madrid)."""

import datetime as dt

from django.utils import timezone
from live.operations import get

from apps.tax.models import TaxCategory
from apps.tax.schemas.calculation import CalculateIn
from apps.tax.schemas.categories import CategoryGetIn
from apps.tax.tests.conftest import HUB_DB, ctx_for, turn_the_rate_at_midnight

pytestmark = HUB_DB

#: 23:30 of 2 November in Bogotá; 05:30 of the 3rd in Madrid.
NIGHT_IN_BOGOTA = dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC)


def test_at_night_elsewhere_the_rate_of_today_is_the_business_s(monkeypatch, in_business_a):
    turn_the_rate_at_midnight(TaxCategory.objects.create(key="test.turn", name="Turn of the night"))
    monkeypatch.setattr(timezone, "now", lambda: NIGHT_IN_BOGOTA)
    monkeypatch.setattr(in_business_a, "timezone", "America/Bogota")
    calculation = get("tax.rate.calculate")(ctx_for(), CalculateIn(amount=1000, tax_category_key="test.turn"))
    assert (calculation.tax_rate_pct, calculation.tax) == (10, 100)
    category = get("tax.category.get")(ctx_for(), CategoryGetIn(key="test.turn"))
    assert category.label == "Turn of the night · 10%"
