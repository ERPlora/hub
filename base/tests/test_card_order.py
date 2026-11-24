"""The order of a write's card (``base.assistant.card_order``): the data that say what it is go first, in the order
named, then what the card computes, then the rest as the form asks it, none twice. A normal card's line shows only its
first three data, so this order is what the person checks before saying yes."""

from base.assistant import card_order


def datum(name: str) -> dict:
    return {"name": name, "label": name.capitalize(), "kind": "text", "value": f"{name} said"}


def names(fields: list[dict]) -> list[str]:
    return [field["name"] for field in fields]


CARD = [datum("method"), datum("day"), datum("amount"), datum("whom"), datum("invoice")]


def test_the_data_named_go_first_in_the_order_named_and_the_rest_as_the_form_asks_them():
    """Two of them said at once: both lead, in the order named, never only the first of them."""
    assert names(card_order.put_first(CARD, ("whom", "invoice", "amount"))) == ["whom", "invoice", "amount", "method", "day"]


def test_a_datum_named_but_not_said_is_skipped():
    assert names(card_order.put_first(CARD, ("whom", "concept", "amount"))) == ["whom", "amount", "method", "day", "invoice"]


def test_what_the_card_computes_goes_right_after_them():
    total = {**datum("total"), "kind": "money", "value": 1250}
    shown = card_order.put_first(CARD, ("whom",), total)
    assert names(shown) == ["whom", "total", "method", "day", "amount", "invoice"]
    assert shown[1] is total


def test_a_datum_computed_takes_the_place_of_the_one_said_by_its_name():
    amount = {**datum("amount"), "kind": "money", "value": 1250}
    shown = card_order.put_first(CARD, ("whom",), amount)
    assert names(shown) == ["whom", "amount", "method", "day", "invoice"]
    assert shown[1] is amount


def test_the_data_left_out_are_not_on_the_card():
    assert names(card_order.put_first(CARD, ("whom",), dropped=("day", "invoice"))) == ["whom", "method", "amount"]


def test_each_datum_is_the_one_the_card_drew():
    assert card_order.put_first(CARD, ("invoice",)) == [CARD[4], *CARD[:4]]


def test_a_summary_that_only_puts_some_data_first():
    summary = card_order.said_first("whom", "invoice", "amount")
    assert summary(None, {}, CARD) == card_order.put_first(CARD, ("whom", "invoice", "amount"))
