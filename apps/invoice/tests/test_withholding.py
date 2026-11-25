"""The arithmetic of the IRPF withholding: a rate of the closed list over the whole base, rounded once and half away from
zero, with the base's sign."""

from decimal import Decimal

import pytest

from apps.invoice.withholding import RATES, columns, withheld


def test_the_rates_are_the_usual_ones_of_the_tax_agency_s_table():
    assert RATES == (15, 7, 1, 19)


@pytest.mark.parametrize(
    ("base", "rate", "amount"),
    [
        (10000, 15, 1500),
        (10000, 7, 700),
        (10000, 1, 100),
        (10000, 19, 1900),
        # 1.50 cents and 4.35: a half goes up, less than a half goes down.
        (10, 15, 2),
        (29, 15, 4),
        (0, 15, 0),
        # A rectifying invoice takes back exactly what its original withheld.
        (-10000, 15, -1500),
        (-10, 15, -2),
        # As the database gives the rate back.
        (10000, Decimal("15.00"), 1500),
    ],
)
def test_what_is_withheld_of_a_base(base, rate, amount):
    assert withheld(base, rate) == amount


def test_without_a_rate_nothing_is_withheld():
    assert withheld(10000, None) == 0


def test_what_a_document_keeps_of_it():
    assert columns(10000, 15) == {"withholding_rate": 15, "withholding_amount": 1500}
    assert columns(10000, None) == {"withholding_rate": None, "withholding_amount": 0}
