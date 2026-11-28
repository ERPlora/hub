"""What a count of the drawer must bring (CASH_REGISTER-F06): some note or coin counted, or a total typed by hand.
A count that counts nothing is refused before the operation runs, from the window, the assistant or the API."""

import pydantic
import pytest

from apps.cash_register.schemas.counts import CountAddIn


def refused(**data) -> list[str]:
    with pytest.raises(pydantic.ValidationError) as caught:
        CountAddIn.model_validate(data)
    return [".".join(str(p) for p in error["loc"]) for error in caught.value.errors()]


def test_a_count_with_neither_notes_and_coins_nor_a_total_is_refused():
    assert refused() == [""]
    assert refused(type="opening", notes="evening") == [""]


def test_a_breakdown_that_counts_nothing_is_refused():
    # The window sends its empty boxes as an empty breakdown; a box at zero counts nothing either.
    assert refused(denominations={}) == [""]
    assert refused(denominations={"bills": {}, "coins": {}}) == [""]
    assert refused(denominations={"bills": {"50": 0}, "coins": {"0.50": 0}}) == [""]


def test_one_note_or_coin_counted_is_a_count():
    assert CountAddIn.model_validate({"denominations": {"bills": {"5": 1}}}).denominations.bills == {"5": 1}
    assert CountAddIn.model_validate({"denominations": {"bills": {"50": 0}, "coins": {"0.01": 1}}}).total is None


def test_a_typed_total_is_a_count_even_at_zero():
    assert CountAddIn.model_validate({"total": 0}).total == 0
    assert CountAddIn.model_validate({"denominations": {"bills": {}}, "total": 0}).total == 0
