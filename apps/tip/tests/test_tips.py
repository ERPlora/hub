"""Recording a tip (TIP-F03, TIP-F04, TIP-F05): kept with its sale, its person and its payment method, and entered in the
open drawer as Tips' own line (CASH_REGISTER-F18); a cash tip with the drawer on and closed is refused, and the same
attempt never records it twice."""

import dataclasses

import pydantic
import pytest
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent

from apps.cash_register.models import Movement
from apps.tip.models import Tip
from apps.tip.schemas import TipAddIn
from apps.tip.services import tips

from .conftest import (
    CARD,
    HUB_DB,
    add_tip,
    as_user,
    charge,
    ctx_for,
    member,
    open_session,
    refund,
    run,
    void,
)

pytestmark = HUB_DB


def summary(session):
    return run("cash_register.session.get", {"session_id": str(session.id)}).summary


def tips_lines(session) -> dict[str, int]:
    return {line.label: line.amount for line in summary(session).app_lines}


def added_events():
    return [event.payload for event in OutboxEvent.objects.filter(name="tip.tip.added").order_by("created_at", "id")]


def test_a_card_tip_on_a_sale_is_kept_with_its_sale_its_person_and_its_payment_method(coffee):
    bea = member("Bea")
    sale = charge(payments=CARD, staff_id=str(bea.id))
    tip = add_tip(150, "card", sale_id=str(sale.id))
    assert (tip.sale_id, tip.sale_number, tip.member_id, tip.member_name) == (sale.id, sale.number, bea.id, "Bea Ruiz")
    assert (tip.method_type, tip.method_name, tip.amount, tip.status, tip.pool) == ("card", "Card", 150, "active", False)
    assert added_events() == [
        {
            "tip_id": str(tip.id),
            "sale_id": str(sale.id),
            "sale_number": sale.number,
            "member_id": str(bea.id),
            "method_type": "card",
            "amount": 150,
        }
    ]


def test_the_person_named_wins_over_whoever_served_the_sale(coffee):
    bea, ana = member("Bea"), member("Ana")
    sale = charge(payments=CARD, staff_id=str(bea.id))
    assert add_tip(150, sale_id=str(sale.id), member_id=str(ana.id)).member_id == ana.id


def test_a_sale_served_by_nobody_leaves_its_tip_unassigned(coffee):
    sale = charge(payments=CARD)
    tip = add_tip(150, sale=sale.number)
    assert (tip.sale_id, tip.member_id, tip.member_name) == (sale.id, None, "")


def test_a_person_who_is_not_on_the_team_is_refused(coffee):
    sale = charge(payments=CARD)
    with pytest.raises(Conflict) as refused:
        add_tip(150, sale_id=str(sale.id), member_id="0190f0f0-0000-7000-8000-000000000000")
    assert refused.value.code == "tip.member_not_found"
    assert not Tip.objects.exists()


def test_a_tip_to_the_pool_has_no_sale_nor_person_and_is_cash():
    session = open_session()
    tip = run("tip.tip.add", {"amount": 500, "pool": True})
    assert (tip.pool, tip.sale_id, tip.member_id, tip.method_type) == (True, None, None, "cash")
    assert tips_lines(session)["Tips in cash"] == 500


def test_a_voided_sale_takes_no_tip(coffee):
    sale = charge(payments=CARD)
    void(sale)
    with pytest.raises(Conflict) as refused:
        add_tip(150, sale_id=str(sale.id))
    assert refused.value.code == "tip.sale_voided"


def test_a_sale_refunded_whole_takes_no_tip(coffee):
    sale = charge(payments=CARD)
    refund(sale, sale.total)
    with pytest.raises(Conflict) as refused:
        add_tip(150, sale_id=str(sale.id))
    assert refused.value.code == "tip.sale_voided"


def test_a_sale_refunded_in_part_still_takes_a_tip(coffee):
    sale = charge("2", payments=CARD)
    refund(sale, 150)
    assert add_tip(150, sale_id=str(sale.id)).status == "active"


def test_a_sale_that_does_not_exist_is_not_found():
    with pytest.raises(Conflict) as refused:
        add_tip(150, sale="20990101-0001")
    assert refused.value.code == "tip.sale_not_found"


def test_the_same_attempt_records_the_tip_once(coffee):
    session = open_session()
    sale = charge(payments=CARD)
    first = add_tip(150, sale_id=str(sale.id), attempt_key="charge-0001:1")
    again = add_tip(150, sale_id=str(sale.id), attempt_key="charge-0001:1")
    assert again.id == first.id
    assert (Tip.objects.count(), len(added_events()), Movement.objects.filter(app="tip").count()) == (1, 1, 1)
    assert tips_lines(session)["Tips by card"] == 150


def test_a_retry_that_lands_while_the_first_is_being_recorded_is_refused_and_records_nothing(coffee, monkeypatch):
    open_session()
    sale = charge(payments=CARD)
    add_tip(150, sale_id=str(sale.id), attempt_key="charge-0002:1")
    # The other request has not committed yet when this one looks for the attempt.
    monkeypatch.setattr(tips, "_attempted", lambda key: None)
    with pytest.raises(Conflict) as refused:
        add_tip(150, sale_id=str(sale.id), attempt_key="charge-0002:1")
    assert refused.value.code == "tip.attempt_in_progress"
    assert (Tip.objects.count(), len(added_events()), Movement.objects.filter(app="tip").count()) == (1, 1, 1)


def test_the_same_attempt_with_another_tip_is_refused(coffee):
    sale = charge(payments=CARD)
    add_tip(150, sale_id=str(sale.id), attempt_key="charge-0001:1")
    with pytest.raises(Conflict) as refused:
        add_tip(200, sale_id=str(sale.id), attempt_key="charge-0001:1")
    assert refused.value.code == "tip.attempt_key_reused"
    assert Tip.objects.count() == 1


@pytest.mark.parametrize(
    "data",
    [
        {"amount": 100, "method": "card"},
        {"amount": 100, "pool": True, "sale": "20261114-0007"},
        {"amount": 100, "pool": True, "method": "card"},
        {"amount": 100, "sale": "20261114-0007"},
        {"amount": 0, "pool": True},
        {"amount": -5, "pool": True},
    ],
)
def test_a_tip_names_its_sale_and_its_payment_method_or_goes_to_the_pool_in_cash_with_a_positive_amount(data):
    with pytest.raises(pydantic.ValidationError):
        TipAddIn.model_validate(data)


def test_an_employee_records_tips_and_whoever_may_not_is_refused(coffee, make_user):
    sale = charge(payments=CARD)
    employee = as_user(make_user("bea", role="hub_employee"))
    assert add_tip(150, sale_id=str(sale.id), ctx=employee).amount == 150
    only_views = dataclasses.replace(employee, permissions=frozenset({"tip.view_tip"}))
    with pytest.raises(PermissionDenied):
        add_tip(150, sale_id=str(sale.id), ctx=only_views)


# Adjusting and voiding a tip (TIP-F06)


def adjust(tip, reason: str = "the card terminal charged 1 € more", ctx=None, **changes):
    return run("tip.tip.update", {"id": str(tip.id), "reason": reason, **changes}, ctx)


def void_tip(tip, reason: str = "typed on the wrong sale", ctx=None):
    return run("tip.tip.void", {"id": str(tip.id), "reason": reason}, ctx)


def tip_movements() -> list[tuple[str, str, int]]:
    return list(Movement.objects.filter(app="tip").order_by("created_at", "id").values_list("type", "method_type", "amount"))


def test_raising_a_tip_enters_the_difference_in_the_open_drawer_and_says_who_why_and_what_changed(coffee):
    session = open_session()
    sale = charge()
    tip = add_tip(300, "cash", sale_id=str(sale.id))
    adjusted = adjust(tip, amount=500)
    assert (adjusted.amount, adjusted.adjust_reason, adjusted.adjusted_by) == (500, "the card terminal charged 1 € more", "tester")
    assert tip_movements() == [("in", "cash", 300), ("in", "cash", 200)]
    assert tips_lines(session)["Tips in cash"] == 500
    event = OutboxEvent.objects.get(name="tip.tip.adjusted")
    assert event.payload == {
        "tip_id": str(tip.id),
        "sale_id": str(sale.id),
        "before": {"amount": 300, "member_id": None},
        "after": {"amount": 500, "member_id": None},
        "reason": "the card terminal charged 1 € more",
    }


def test_giving_a_tip_to_somebody_else_moves_no_money(coffee):
    open_session()
    bea = member("Bea")
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    adjusted = adjust(tip, member_id=str(bea.id))
    assert (adjusted.member_id, adjusted.member_name, adjusted.amount) == (bea.id, "Bea Ruiz", 300)
    assert tip_movements() == [("in", "card", 300)]


def test_a_change_needs_its_reason():
    with pytest.raises(pydantic.ValidationError):
        run("tip.tip.update", {"id": "0190f0f0-0000-7000-8000-000000000000", "amount": 100, "reason": "  "})


def test_an_adjustment_that_changes_nothing_records_nothing(coffee):
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    assert adjust(tip, amount=300).adjusted_at is None
    assert not OutboxEvent.objects.filter(name="tip.tip.adjusted").exists()


def test_voiding_a_tip_takes_it_out_of_the_open_drawer_and_says_who_and_why(coffee):
    session = open_session()
    sale = charge()
    tip = add_tip(300, "cash", sale_id=str(sale.id))
    voided = void_tip(tip)
    assert (voided.status, voided.void_reason, voided.voided_by) == ("voided", "typed on the wrong sale", "tester")
    assert voided.voided_at is not None
    assert tip_movements() == [("in", "cash", 300), ("out", "cash", 300)]
    assert tips_lines(session) == {"Tips in cash": 300, "Tips by card": 0, "Tips paid out": -300}
    assert OutboxEvent.objects.get(name="tip.tip.voided").payload == {
        "tip_id": str(tip.id),
        "sale_id": str(sale.id),
        "amount": 300,
        "method_type": "cash",
        "reason": "typed on the wrong sale",
    }


def test_a_voided_tip_is_neither_voided_again_nor_adjusted(coffee):
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    void_tip(tip)
    for change in (lambda: void_tip(tip), lambda: adjust(tip, amount=100)):
        with pytest.raises(Conflict) as refused:
            change()
        assert refused.value.code == "tip.tip_voided"


def test_only_whoever_manages_tips_adjusts_or_voids_them(coffee, make_user):
    sale = charge(payments=CARD)
    tip = add_tip(300, "card", sale_id=str(sale.id))
    employee = as_user(make_user("bea", role="hub_employee"))
    for change in (lambda: adjust(tip, amount=100, ctx=employee), lambda: void_tip(tip, ctx=employee)):
        with pytest.raises(PermissionDenied):
            change()
    assert void_tip(tip, ctx=ctx_for("hub_manager")).status == "voided"
