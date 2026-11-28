"""A session: its list's order and money filters, how one is named, and its opening float."""

from apps.cash_register.schemas.sessions import SessionCloseIn, SessionGetIn, SessionListIn, SessionOpenIn
from apps.cash_register.tests.schema_checks import refused


def test_the_session_list_sorts_newest_first_and_filters_by_money():
    params = SessionListIn.model_validate({})
    assert (params.sort, params.dir) == ("opened_at", "desc")
    # A short drawer is a negative difference: the filter takes it.
    assert SessionListIn.model_validate({"difference_max": -1}).difference_max == -1
    assert refused(SessionListIn, opening_min=-1) == ["opening_min"]
    assert refused(SessionListIn, status="suspended") == ["status"]
    assert refused(SessionListIn, sort="id; drop") == ["sort"]


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
