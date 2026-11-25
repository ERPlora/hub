"""What a tip moves in the drawer (CASH_REGISTER-F18): Tips' own line in the open session, in its payment method; a
cash tip with the drawer on and closed is refused, with the drawer off it is kept in Tips only, and a closed session is
never touched: what changes later goes into the open one."""

import pytest
from live.errors import Conflict

from apps.cash_register.models import Movement
from apps.tip.models import Tip

from .conftest import CARD, HUB_DB, add_tip, charge, open_session, run
from .test_tips import (
    added_events,
    adjust,
    summary,
    tip_movements,
    tips_lines,
    void_tip,
)

pytestmark = HUB_DB


def drawer_off():
    run("cash_register.settings.update", {"enable_cash_register": False})


def test_a_cash_tip_enters_the_open_drawer_as_a_line_of_tips_and_raises_the_expected_cash(coffee):
    session = open_session(10000)
    sale = charge()
    before = summary(session).expected_cash
    tip = add_tip(300, "cash", sale_id=str(sale.id))
    assert summary(session).expected_cash == before + 300
    assert tips_lines(session) == {"Tips in cash": 300, "Tips by card": 0, "Tips paid out": 0}
    movement = Movement.objects.get(app="tip")
    assert (movement.type, movement.method_type, movement.amount, movement.session_id) == ("in", "cash", 300, session.id)
    assert movement.description == sale.number
    assert Tip.objects.get(pk=tip.id).session_id == session.id


def test_a_card_tip_shows_apart_in_the_open_drawer_without_touching_the_expected_cash(coffee):
    session = open_session(10000)
    sale = charge(payments=CARD)
    before = summary(session).expected_cash
    add_tip(150, "card", sale_id=str(sale.id))
    assert summary(session).expected_cash == before
    assert tips_lines(session)["Tips by card"] == 150


def test_a_cash_tip_with_the_drawer_on_and_closed_is_refused_and_nothing_is_kept(coffee):
    sale = charge(payments=CARD)
    with pytest.raises(Conflict) as refused:
        add_tip(300, "cash", sale_id=str(sale.id))
    assert refused.value.code == "tip.cash_register_closed"
    assert (Tip.objects.count(), added_events()) == (0, [])


def test_with_the_drawer_off_a_cash_tip_is_kept_in_tips_only(coffee):
    drawer_off()
    sale = charge()
    tip = add_tip(300, "cash", sale_id=str(sale.id))
    assert Tip.objects.get(pk=tip.id).session_id is None
    assert not Movement.objects.exists()


def test_a_card_tip_with_the_drawer_closed_is_kept_without_a_drawer_line(coffee):
    sale = charge(payments=CARD)
    tip = add_tip(150, "card", sale_id=str(sale.id))
    assert Tip.objects.get(pk=tip.id).session_id is None
    assert not Movement.objects.exists()


def test_lowering_a_card_tip_takes_the_difference_off_its_line(coffee):
    session = open_session()
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    adjust(tip, amount=100)
    assert tip_movements() == [("in", "card", 300), ("out", "card", 200)]
    assert tips_lines(session)["Tips by card"] == 100


def test_a_tip_that_never_entered_a_drawer_moves_none_when_it_changes(coffee):
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    open_session()
    adjust(tip, amount=500)
    void_tip(tip)
    assert tip_movements() == []


def test_a_closed_session_is_never_touched_the_change_goes_into_the_open_one(coffee):
    first = open_session()
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    run("cash_register.session.close", {"closing_balance": 10000})
    second = open_session()
    void_tip(tip)
    assert tips_lines(first)["Tips by card"] == 300
    assert tips_lines(second)["Tips by card"] == -300


def test_with_no_session_open_a_change_is_kept_in_tips_only(coffee):
    open_session()
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    run("cash_register.session.close", {"closing_balance": 10000})
    assert void_tip(tip).status == "voided"
    assert tip_movements() == [("in", "card", 300)]


