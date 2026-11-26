"""The numbers of the sales: one counter per business day and the number it gives."""

import datetime as dt

from apps.sale.models.numbering import SaleCounter, sale_number
from apps.sale.tests.conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_the_sale_number_is_the_day_and_a_counter_of_at_least_four_digits():
    day = dt.date(2026, 9, 1)
    assert sale_number(day, 7) == "20260901-0007"
    assert sale_number(day, 1000) == "20260901-1000"
    # A minimum width, never a ceiling: the 10.000th sale is not rewritten as 1000.
    assert sale_number(day, 10000) == "20260901-10000"
    assert sale_number(day, 1000000) == "20260901-1000000"


def test_one_counter_per_business_day():
    SaleCounter.objects.create(day=dt.date(2026, 10, 14), last=1)
    refused(lambda: SaleCounter.objects.create(day=dt.date(2026, 10, 14), last=1))
