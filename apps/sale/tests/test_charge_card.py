"""The card of a charge through the assistant (``sale.sale.complete``): how much it charges and how, as the charge
sheet's button says it («Cobrar 1,50 €» in cash), never «Payments: 1 item» nor the check's version, which only the
charge sheet needs (hub#2279). The total is the server's, as its preview values it for whoever asks; a tender without
an amount pays what the others leave, and none at all is cash for the whole, as the charge takes it.
"""

import pytest
from live.assistant import NAMED
from live.operations import get

from apps.sale.tests.conftest import HUB_DB, ctx_for, run
from base import assistant

pytestmark = HUB_DB

KEY = "card-attempt-0001"
CHARGES = ("sale.sale.complete", "sale.sale.complete_over_limit")


def drawn(arguments: dict, language: str = "es", write: str = "sale.sale.complete", ctx=None) -> dict:
    return assistant.cards.card(
        get(write), {"idempotency_key": KEY, **arguments}, language, ctx or ctx_for(language=language)
    )


def card_fields(arguments: dict, language: str = "es", write: str = "sale.sale.complete", ctx=None) -> dict:
    return {field["name"]: field for field in drawn(arguments, language, write, ctx)["fields"]}


def money(cents: int) -> dict:
    return {"kind": "money", "value": cents}


@pytest.fixture
def espresso(product):
    return product("Espresso", "ESP", 150, "restaurant.drink")


@pytest.fixture
def check(espresso, product):
    tonic = product("Tonic", "TON", 250, "restaurant.drink")
    return run(
        "sale.order.open",
        {"label": "Table 4", "lines": [{"product_id": str(espresso.id)}, {"product_id": str(tonic.id)}]},
    )


@pytest.mark.parametrize("write", CHARGES)
@pytest.mark.parametrize(("language", "cash"), [("es", "Efectivo"), ("en", "Cash")])
def test_a_counter_sale_in_cash_says_its_total_and_that_cash_pays_it(espresso, write, language, cash):
    shown = card_fields(
        {"lines": [{"product_id": str(espresso.id)}], "payments": [{"method": "cash"}]}, language, write
    )
    assert list(shown) == ["lines", "total", "payments"]
    assert (shown["total"]["kind"], shown["total"]["value"]) == ("money", 150)
    payments = shown["payments"]
    assert (payments["kind"], payments["value"], payments.get(NAMED)) == (
        "list",
        [{"method": cash, "amount": money(150)}],
        True,
    )


@pytest.mark.parametrize(("language", "labels"), [("es", ("Total", "Pagos")), ("en", ("Total", "Payments"))])
def test_the_total_and_the_payments_are_named_in_the_persons_language(espresso, language, labels):
    shown = card_fields({"lines": [{"product_id": str(espresso.id)}]}, language)
    assert (shown["total"]["label"], shown["payments"]["label"]) == labels


def test_a_charge_that_names_no_tender_says_cash_for_the_whole_as_the_charge_takes_it(espresso):
    shown = card_fields({"lines": [{"product_id": str(espresso.id)}, {"product_id": str(espresso.id)}]})
    assert shown["total"]["value"] == 300
    assert shown["payments"]["value"] == [{"method": "Efectivo", "amount": money(300)}]


def test_a_check_says_what_it_comes_to_and_not_its_version(check):
    shown = card_fields(
        {"order_id": str(check.id), "order_version": check.version, "payments": [{"method": "efectivo"}]}
    )
    assert list(shown) == ["order_id", "total", "payments"]
    assert shown["total"]["value"] == 400
    assert shown["payments"]["value"] == [{"method": "Efectivo", "amount": money(400)}]


def test_a_partial_charge_says_what_those_lines_come_to(check):
    espresso_line = next(line for line in check.lines if line.name == "Espresso")
    shown = card_fields(
        {"order_id": str(check.id), "line_ids": [str(espresso_line.id)], "payments": [{"method": "card"}]}
    )
    assert shown["total"]["value"] == 150
    assert shown["payments"]["value"] == [{"method": "Tarjeta", "amount": money(150)}]


def test_a_split_says_each_tender_and_the_one_without_an_amount_pays_the_rest(check):
    shown = card_fields(
        {"order_id": str(check.id), "payments": [{"method": "card", "amount": 100}, {"method": "cash"}]}
    )
    assert shown["payments"]["value"] == [
        {"method": "Tarjeta", "amount": money(100)},
        {"method": "Efectivo", "amount": money(300)},
    ]


def test_a_tender_by_its_id_is_said_by_its_name(espresso):
    card = next(row for row in run("sale.payment_method.list", {}).rows if row.type == "card")
    shown = card_fields({"lines": [{"product_id": str(espresso.id)}], "payments": [{"method_id": str(card.id)}]})
    assert shown["payments"]["value"] == [{"method": "Tarjeta", "amount": money(150)}]


def test_tenders_that_do_not_add_up_are_said_as_sent_and_the_charge_refuses_them(check):
    """Two tenders without an amount, or amounts over the total: the card says what was sent, each by its method,
    beside the total, so the person sees it does not add up; the charge refuses it on its own."""
    two_open = card_fields({"order_id": str(check.id), "payments": [{"method": "card"}, {"method": "cash"}]})
    assert two_open["payments"]["value"] == [{"method": "Tarjeta"}, {"method": "Efectivo"}]
    over = card_fields({"order_id": str(check.id), "payments": [{"method": "card", "amount": 900}, {"method": "cash"}]})
    assert over["payments"]["value"] == [{"method": "Tarjeta", "amount": money(900)}, {"method": "Efectivo"}]


def test_a_method_the_business_does_not_have_is_said_as_said(espresso):
    shown = card_fields({"lines": [{"product_id": str(espresso.id)}], "payments": [{"method": "Bizum"}]})
    assert shown["payments"]["value"] == [{"method": "Bizum", "amount": money(150)}]


def test_what_cannot_be_valued_is_left_as_its_data_say_it_and_the_charge_refuses_it():
    """Nothing to charge (no check, no lines): no total is made up, and the card keeps its data as sent."""
    shown = card_fields({"payments": [{"method": "cash"}]})
    assert "total" not in shown
    assert shown["payments"]["value"] == [{"method": "cash"}]


def test_a_check_that_is_not_there_is_not_valued(check):
    """A check this person cannot read, or no longer there: no total is made up; the charge refuses it on its own."""
    shown = card_fields({"order_id": "01a20000-0000-7000-8000-000000000000", "payments": [{"method": "cash"}]})
    assert "total" not in shown
    assert shown["payments"]["value"] == [{"method": "cash"}]


def test_the_yes_is_for_that_total(check, espresso):
    """A line added to the check after the card was drawn changes what it charges: drawn again with the yes, the
    card is another one, and the yes runs nothing (``fingerprint``)."""
    arguments = {"order_id": str(check.id), "payments": [{"method": "cash"}]}
    before = assistant.cards.fingerprint(drawn(arguments), [])
    run("sale.order.add_line", {"order_id": str(check.id), "product_id": str(espresso.id)})
    assert assistant.cards.fingerprint(drawn(arguments), []) != before
