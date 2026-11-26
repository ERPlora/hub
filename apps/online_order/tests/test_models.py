"""A table's code: one per table, unique across the business, with a UUIDv7 key. An order a table sends waits as
pending, each of its lines a dish or a set menu."""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.online_order.models import Order, OrderLine, TableCode

from .conftest import HUB_DB

pytestmark = HUB_DB


def test_the_key_is_a_uuid7():
    code = TableCode.objects.create(table_id=uuid.uuid7(), code="abc")
    assert code.id.version == 7


def test_a_table_has_one_code():
    table_id = uuid.uuid7()
    TableCode.objects.create(table_id=table_id, code="first")
    with pytest.raises(IntegrityError), transaction.atomic():
        TableCode.objects.create(table_id=table_id, code="second")


def test_two_tables_never_share_a_code():
    TableCode.objects.create(table_id=uuid.uuid7(), code="same")
    with pytest.raises(IntegrityError), transaction.atomic():
        TableCode.objects.create(table_id=uuid.uuid7(), code="same")


def test_an_order_waits_as_pending_with_a_uuid7_key():
    order = Order.objects.create(table_id=uuid.uuid7(), total=750)
    assert (order.id.version, order.status) == (7, Order.Status.PENDING)


@pytest.mark.parametrize("named", [{}, {"product_id": uuid.uuid7(), "combo_id": uuid.uuid7()}])
def test_a_line_is_a_dish_or_a_set_menu_never_both_nor_neither(named):
    order = Order.objects.create(table_id=uuid.uuid7(), total=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderLine.objects.create(order=order, position=0, name="Croquettes", quantity=1, unit_price=750, **named)
