"""Online booking with the real Customers app (no doubles): the card found or created by the mobile. Two cards
merged and a customer's data erased reach the inbox through the worker's real relay: ``test_relay.py``.
"""

import pytest

from apps.customer.models import Customer

from .conftest import booking_data, public, run

pytestmark = pytest.mark.django_db


def test_a_new_mobile_is_a_new_card_that_customers_finds_by_its_number(salon):
    public(
        "book", booking_data(salon, "10:00", phone="+34 699 000 111", name="Nora Vidal")
    )
    found = run("customer.customer.by_phone", {"phone": "699000111"})
    assert [card.name for card in found.rows] == ["Nora Vidal"]
    assert found.rows[0].phone == "+34699000111"


def test_a_known_mobile_books_on_the_card_customers_already_has(salon):
    public(
        "book", booking_data(salon, "10:00", phone="600 111 222", name="Lucía Pérez")
    )
    assert Customer.objects.filter(phone="+34600111222").count() == 1
    assert run("online_booking.booking.list").rows[0].customer_id == salon.lucia.id
