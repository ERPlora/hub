"""A sale's day at night in a business of another zone (hub#771). A sale's day, and the «today» of Taxes that its
figures and its preview read, are still on the deployment's clock: they reach the VeriFactu record, so they move
together, under supervision (hub#772; ``tests/test_guardrails_fiscal_clock.py`` freezes the record). Until then the till
stays on one clock, whole: it never says one day and charges on another."""

import datetime as dt
import uuid

import pytest

from apps.sale.tests.conftest import run
from apps.tax.models import TaxCategory, TaxRule

pytestmark = pytest.mark.django_db

#: The day of a sale at night in another zone (``night_elsewhere``): the deployment's, until hub#772.
SALE_DAY = dt.date(2026, 11, 3)


@pytest.fixture
def tapa(product, night_elsewhere):
    """A product of a category whose rate changes at the turn of the night: 10 % until the 2nd, 21 % from the 3rd."""
    category = TaxCategory.objects.create(key="test.turn", name="Turn of the night")
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="10", valid_to=dt.date(2026, 11, 2))
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="21", valid_from=SALE_DAY)
    product("Tapa", "TAP", 1000, "test.turn")
    return category


LINES = [{"product": "TAP"}]


def charge():
    return run(
        "sale.sale.complete",
        {"idempotency_key": str(uuid.uuid7()), "lines": LINES, "payments": [{"method": "card"}]},
    )


def test_the_till_counts_a_sale_on_the_day_it_numbers_it(tapa):
    sale = charge()
    assert sale.business_day == SALE_DAY
    assert run("sale.business_day.get").today == SALE_DAY
    today = run("sale.sale.today")
    assert (today.day, today.tickets, today.total) == (SALE_DAY, 1, sale.total)
    assert run("sale.sale.last_7_days").rows[-1].total == sale.total


def test_a_session_done_outside_the_till_counts_on_the_day_the_till_charges(tapa):
    # SALE-F28, SERVICE-F21: what a professional produced is on one clock, the till's, which hub#772 moves whole.
    sale = charge()
    ana = uuid.uuid7()
    done = run("sale.voucher_session.record", {"session_id": str(uuid.uuid7()), "staff_id": str(ana), "value": 3333})
    assert (done.business_day, sale.business_day) == (SALE_DAY, SALE_DAY)
    [row] = [row for row in run("sale.sale.by_staff", {"date_from": str(SALE_DAY)}).rows if row.staff_id == ana]
    assert row.voucher_total == 3333


def test_the_preview_and_the_charge_tax_on_the_same_day(tapa):
    preview = run("sale.checkout.preview", {"lines": LINES})
    sale = charge()
    assert (preview.tax_total, preview.total) == (sale.tax_total, sale.total)


def test_the_cash_limit_values_the_rest_of_a_check_on_the_day_it_would_be_charged(tapa):
    run("sale.settings.update", {"default_tax_included": False})
    order = run("sale.order.open", {"lines": LINES + LINES})
    first = order.lines[0]
    preview = run("sale.checkout.preview", {"order_id": str(order.id), "line_ids": [str(first.id)]})
    # Both lines at 21 % (12.10 € each): at the other day's 10 %, the whole check would be 22 €.
    assert (preview.total, preview.operation_total) == (1210, 2420)


def test_a_section_says_the_rate_the_till_charges(tapa):
    run("sale.department.create", {"name": "Fruit", "tax_category_key": "test.turn"})
    assert run("sale.department.list").rows[0].tax_rate_pct == 21
