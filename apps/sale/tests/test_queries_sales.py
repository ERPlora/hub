"""The sales list reads every tender of a sale, not only the largest one (SALE-F28, SALE-F03)."""

import pytest
from django.utils import translation

from apps.sale.tests.conftest import HUB_DB, ctx_for, run

pytestmark = HUB_DB

#: 5,00 paid with 2,00 in cash and 3,00 by card: the card is the larger tender.
SPLIT = [
    {"method": "cash", "amount": 200, "tendered": 200},
    {"method": "card", "amount": 300},
]


@pytest.fixture
def menu(product):
    product("Menu", "MNU", 500, "restaurant.food")


def charge(key: str, payments: list[dict]):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": [{"product": "MNU"}], "payments": payments},
    )


def listed(**params) -> list:
    return run("sale.sale.list", params).rows


def test_a_sale_paid_with_two_methods_says_both_in_the_order_they_were_taken(menu):
    split = charge("tenders-key-0001", SPLIT)
    (row,) = listed()
    assert (row.id, row.payment_method_name) == (split.id, "Cash + Card")


def test_the_methods_of_a_split_sale_read_in_the_readers_language(menu):
    charge("tenders-key-0001", SPLIT)
    with translation.override("es"):
        (row,) = run("sale.sale.list", {}, ctx_for(language="es")).rows
    assert row.payment_method_name == "Efectivo + Tarjeta"


def test_a_method_tendered_twice_is_said_once(menu):
    charge("tenders-key-0001", [{"method": "card", "amount": 200}, {"method": "card"}])
    (row,) = listed()
    assert row.payment_method_name == "Card"


def test_a_sale_paid_with_one_method_still_says_just_that_one(menu):
    cash = charge("tenders-key-0001", [{"method": "cash", "tendered": 1000}])
    (row,) = listed()
    assert (row.id, row.payment_method_name) == (cash.id, "Cash")


def test_the_payment_filter_finds_a_split_sale_by_any_of_its_methods(menu):
    split = charge("tenders-key-0001", SPLIT)
    cash = charge("tenders-key-0002", [{"method": "cash", "tendered": 500}])
    card = charge("tenders-key-0003", [{"method": "card"}])
    assert {row.id for row in listed(payment_method_name="Cash")} == {split.id, cash.id}
    assert {row.id for row in listed(payment_method_name="Card")} == {split.id, card.id}


def test_a_sale_with_two_tenders_of_the_filtered_method_is_listed_once(menu):
    twice = charge("tenders-key-0001", [{"method": "card", "amount": 200}, {"method": "card"}])
    page = run("sale.sale.list", {"payment_method_name": "Card"})
    assert ([row.id for row in page.rows], page.total) == ([twice.id], 1)


def test_sorting_by_payment_follows_what_the_column_says(menu):
    split = charge("tenders-key-0001", SPLIT)
    cash = charge("tenders-key-0002", [{"method": "cash", "tendered": 500}])
    card = charge("tenders-key-0003", [{"method": "card"}])
    rows = listed(sort="payment_method_name", dir="asc")
    assert [row.id for row in rows] == [card.id, cash.id, split.id]
