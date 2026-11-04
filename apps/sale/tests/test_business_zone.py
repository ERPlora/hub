"""A sale's day at night in a business of another zone (hub#771). Every other «today» of a business reads its clock; a
sale's cannot yet: Invoicing copies its day to the operation date of the VeriFactu record and its number to the record's
description, while the issue date stays on the deployment's clock until hub#772 moves it, under supervision. Until then
a sale stays on one clock, whole: the till never says one day and charges on another, and no record changes."""

import datetime as dt
import uuid

import pytest

from apps.invoice.models import Invoice
from apps.sale.tests.conftest import run
from apps.sale.tests.test_integration_invoice import ISSUER
from apps.tax.models import TaxCategory, TaxRule
from apps.verifactu.services import _alta_fields

pytestmark = pytest.mark.django_db

#: The day of a sale at 23:30 in the Canaries: the deployment's, until hub#772.
SALE_DAY = dt.date(2026, 11, 3)


@pytest.fixture
def tapa(product, canary_at_night):
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


def test_the_record_of_a_sale_at_night_says_no_other_day_than_its_issue(tapa):
    run("invoice.issuer.update", ISSUER)
    sale = charge()
    invoice = Invoice.objects.get(source_sale_id=sale.id)
    assert (invoice.issue_date, invoice.operation_date) == (SALE_DAY, SALE_DAY)
    assert _alta_fields(invoice)["operation_date"] is None
    assert sale.number in invoice.description and "20261103" in sale.number
