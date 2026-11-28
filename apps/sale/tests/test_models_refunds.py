"""The refunds: what the database refuses of the money given back."""

import pytest
from django.db import IntegrityError
from live.operations import atomic

from apps.sale.models.refunds import Refund
from apps.sale.tests.conftest import HUB_DB, a_sale

pytestmark = HUB_DB


def test_a_refund_may_give_back_no_money_but_never_a_negative_amount():
    sale = a_sale()
    Refund.objects.create(sale=sale, total=0, reason="only the session")
    with pytest.raises(IntegrityError), atomic():
        Refund.objects.create(sale=sale, total=-1, reason="x")
