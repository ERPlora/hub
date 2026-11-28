"""The lines of a session: a cash in or out by hand, and the list of one session or of the unassigned lines."""

from apps.cash_register.schemas.movements import MovementAddIn, MovementListIn
from apps.cash_register.tests.schema_checks import refused


def test_a_manual_movement_is_cash_in_or_out_of_a_positive_amount():
    movement = MovementAddIn.model_validate({"type": "out", "amount": 2000})
    assert movement.method_type == "cash"
    assert refused(MovementAddIn, type="sale", amount=100) == ["type"]
    assert refused(MovementAddIn, type="in", amount=0) == ["amount"]
    assert refused(MovementAddIn, type="in", amount=-5) == ["amount"]
    assert refused(MovementAddIn, type="in", amount=5, method_type="Efectivo") == [
        "method_type"
    ]


def test_a_movement_list_names_a_session_or_asks_for_the_unassigned_lines():
    MovementListIn.model_validate({"session": "S-261014-0001"})
    MovementListIn.model_validate({"unassigned": True})
    assert refused(MovementListIn) == [""]
    assert refused(MovementListIn, session="S-261014-0001", unassigned=True) == [""]
