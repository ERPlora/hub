"""The tip and the settings rows: what the database itself refuses."""

import pytest
from django.db import IntegrityError
from live.operations import atomic

from apps.sale.models import PaymentMethod
from apps.tip.models import Settings, Tip

from .conftest import HUB_DB

pytestmark = HUB_DB


def cash():
    return PaymentMethod.objects.filter(type="cash", is_active=True).first()


def a_tip(**fields):
    method = cash()
    return Tip.objects.create(
        **{"method": method, "method_name": method.name, "method_type": method.type, "amount": 100, **fields}
    )


def test_its_key_is_a_uuid7():
    assert a_tip().pk.version == 7


def test_a_tip_is_never_zero_nor_negative():
    with pytest.raises(IntegrityError), atomic():
        a_tip(amount=0)


def test_an_attempt_records_one_tip_only():
    a_tip(attempt_key="charge-0001:1")
    with pytest.raises(IntegrityError), atomic():
        a_tip(attempt_key="charge-0001:1")
    a_tip(), a_tip()  # without an attempt key, as many as recorded


def test_there_is_one_row_of_settings_at_most():
    Settings.objects.create()
    with pytest.raises(IntegrityError), atomic():
        Settings.objects.create()


def test_a_tip_reads_as_its_payment_method_and_amount():
    assert str(a_tip()) == f"{cash().name} 100"
