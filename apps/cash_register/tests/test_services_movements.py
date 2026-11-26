"""Cash brought into the drawer or taken out of it (CASH_REGISTER-F05), in the open session."""

import pytest
from live.errors import Conflict, NotFound

from apps.cash_register.models import Movement
from apps.cash_register.tests.conftest import HUB_DB, events, open_session, run, settings

pytestmark = HUB_DB


# ── CASH_REGISTER-F05 Cash in and out ───────────────────────────────────────────────────────────


def test_cash_in_and_out_move_the_expected_with_the_sign_of_their_type():
    session = open_session(10000)
    cash_in = run(
        "cash_register.movement.add",
        {"type": "in", "amount": 2000, "description": "Change"},
    )
    cash_out = run(
        "cash_register.movement.add",
        {"type": "out", "amount": 500, "description": "Supplier"},
    )
    assert (cash_in.signed_amount, cash_out.signed_amount) == (2000, -500)
    assert cash_out.created_by == "tester" and cash_out.session_id == session.id
    current = run("cash_register.session.current")
    assert current.session.expected_balance == 11500
    assert [e["type"] for e in events("cash_register.movement.added")] == ["in", "out"]


def test_a_movement_by_card_is_listed_but_never_in_the_drawer():
    open_session(10000)
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 50000, "method_type": "card"},
    )
    assert run("cash_register.session.current").session.expected_balance == 10000


def test_a_cash_out_cannot_leave_the_drawer_below_zero_unless_allowed():
    open_session(1000)
    with pytest.raises(Conflict) as refused:
        run("cash_register.movement.add", {"type": "out", "amount": 1001})
    assert refused.value.code == "cash_register.negative_balance_not_allowed"
    run("cash_register.movement.add", {"type": "out", "amount": 1000})
    settings(allow_negative_balance=True)
    run("cash_register.movement.add", {"type": "out", "amount": 300})
    assert run("cash_register.session.current").session.expected_balance == -300


def test_a_closed_session_takes_no_movement():
    session = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    with pytest.raises(Conflict) as refused:
        run(
            "cash_register.movement.add",
            {"session_id": str(session.id), "type": "in", "amount": 100},
        )
    assert refused.value.code == "cash_register.session_not_open"
    assert not Movement.objects.exists()


def test_without_an_open_session_there_is_nothing_to_record_in():
    with pytest.raises(Conflict) as refused:
        run("cash_register.movement.add", {"type": "in", "amount": 100})
    assert refused.value.code == "cash_register.no_open_session"


def test_a_session_number_that_does_not_exist_is_not_found():
    with pytest.raises(NotFound) as refused:
        run(
            "cash_register.movement.add",
            {"session": "S-990101-0001", "type": "in", "amount": 100},
        )
    assert refused.value.code == "cash_register.session_not_found"
