"""What every input of the cash register shares: a page of at most a hundred rows, and no field it does not know."""

from apps.cash_register.schemas.movements import MovementAddIn
from apps.cash_register.schemas.sessions import SessionListIn
from apps.cash_register.tests.schema_checks import refused


def test_a_page_has_at_most_a_hundred_rows():
    assert SessionListIn.model_validate({}).limit == 50
    assert SessionListIn.model_validate({"limit": 100}).limit == 100
    assert refused(SessionListIn, limit=101) == ["limit"]
    assert refused(SessionListIn, limit=0) == ["limit"]


def test_an_unknown_filter_is_refused():
    assert refused(SessionListIn, colour="red") == ["colour"]
    assert refused(MovementAddIn, type="in", amount=1, sign=-1) == ["sign"]
