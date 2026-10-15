"""Input schemas of the cash register app: what a 422 refuses before any operation runs."""

import pydantic
import pytest

from apps.cash_register.schemas import (
    CountAddIn,
    CountListIn,
    MovementAddIn,
    MovementListIn,
    RegisterIn,
    RegisterUpdateIn,
    SessionCloseIn,
    SessionGetIn,
    SessionListIn,
    SessionOpenIn,
    SettingsPatchIn,
)


def refused(schema, **data) -> list[str]:
    with pytest.raises(pydantic.ValidationError) as caught:
        schema.model_validate(data)
    return [".".join(str(p) for p in error["loc"]) for error in caught.value.errors()]


def test_a_page_has_at_most_a_hundred_rows():
    assert SessionListIn.model_validate({}).limit == 50
    assert SessionListIn.model_validate({"limit": 100}).limit == 100
    assert refused(SessionListIn, limit=101) == ["limit"]
    assert refused(SessionListIn, limit=0) == ["limit"]


def test_an_unknown_filter_is_refused():
    assert refused(SessionListIn, colour="red") == ["colour"]
    assert refused(MovementAddIn, type="in", amount=1, sign=-1) == ["sign"]


def test_the_session_list_sorts_newest_first_and_filters_by_money():
    params = SessionListIn.model_validate({})
    assert (params.sort, params.dir) == ("opened_at", "desc")
    # A short drawer is a negative difference: the filter takes it.
    assert SessionListIn.model_validate({"difference_max": -1}).difference_max == -1
    assert refused(SessionListIn, opening_min=-1) == ["opening_min"]
    assert refused(SessionListIn, status="suspended") == ["status"]
    assert refused(SessionListIn, sort="id; drop") == ["sort"]


def test_the_auto_close_time_is_a_whole_hour():
    assert (
        SettingsPatchIn.model_validate({"auto_close_time": "23:00"}).auto_close_time
        == "23:00"
    )
    for wrong in ("04:30", "24:00", "4:00", ""):
        assert refused(SettingsPatchIn, auto_close_time=wrong) == ["auto_close_time"]


def test_settings_change_only_what_is_sent():
    patch = SettingsPatchIn.model_validate({"require_blind_count": True})
    assert patch.model_dump(exclude_unset=True) == {"require_blind_count": True}


def test_a_drawer_has_a_name():
    assert RegisterIn.model_validate({"name": "  Bar  "}).name == "Bar"
    assert refused(RegisterIn, name="   ") == ["name"]
    assert refused(RegisterIn, name="x" * 101) == ["name"]


def test_a_drawer_change_names_the_drawer_and_changes_something():
    assert refused(RegisterUpdateIn, name="Terrace") == [""]
    assert refused(RegisterUpdateIn, register_name="Bar") == [""]
    RegisterUpdateIn.model_validate({"register_name": "Bar", "is_active": False})


def test_a_session_is_named_by_its_id_or_its_number():
    assert (
        SessionGetIn.model_validate({"session": " S-261014-0001 "}).session
        == "S-261014-0001"
    )
    assert refused(SessionGetIn) == [""]
    # Closing, recording and counting default to the open session.
    assert SessionCloseIn.model_validate({}).session is None


def test_the_opening_float_is_never_negative():
    assert SessionOpenIn.model_validate({}).opening_balance is None
    assert refused(SessionOpenIn, opening_balance=-1) == ["opening_balance"]


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


def test_a_count_takes_notes_and_coins_or_a_total():
    count = CountAddIn.model_validate(
        {"denominations": {"bills": {"50": 2}, "coins": {"0.50": 3}}}
    )
    assert count.type == "closing"
    assert CountAddIn.model_validate({"total": 0}).total == 0
    assert refused(CountAddIn) == [""]
    assert refused(CountAddIn, denominations={"bills": {"fifty": 2}}) == [
        "denominations.bills.fifty.[key]"
    ]
    assert refused(CountAddIn, denominations={"coins": {"0.50": -1}}) == [
        "denominations.coins.0.50"
    ]
    assert refused(CountAddIn, total=-1) == ["total"]


def test_a_count_list_names_its_session():
    assert refused(CountListIn) == [""]
    CountListIn.model_validate({"session_id": "0199e4f0-0000-7000-8000-000000000000"})
