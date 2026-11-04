"""The reference of the day on the clock of the business, not the deployment's (hub#771). Apart from ``test_services``,
which fixes ``timezone.localdate`` itself for every test."""

import pytest
from live.operations import get

from .conftest import ctx_for, make_method

pytestmark = pytest.mark.django_db


def recorded(bank):
    op = get("payment.payment.create")
    data = {"method_id": str(bank.id), "payment_date": "2026-11-02", "amount": 12_50, "beneficiary_name": "Proveedor Norte"}
    return op(ctx_for(), op.input.model_validate(data)).reference


def test_the_reference_of_the_day_is_of_the_businesss_day(canary_at_night):
    assert recorded(make_method()) == "PAY-20261102-0001"


def test_a_business_that_changes_zone_never_repeats_a_reference(across_a_change_of_zone):
    bank = make_method()
    assert across_a_change_of_zone(lambda: recorded(bank)) == [
        "PAY-20261102-0001",
        "PAY-20261103-0001",
        "PAY-20261102-0002",
    ]
