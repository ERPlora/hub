"""What a count of the drawer reads of the business's currency: its code, its decimals, its notes and its coins."""

import pydantic
import pytest

from apps.cash_register.schemas.currency import CurrencyOut


def test_the_currency_gives_its_code_its_decimals_its_notes_and_its_coins():
    euro = {"currency": "EUR", "decimals": 2, "bills": ["500", "5"], "coins": ["2", "0.01"]}
    assert CurrencyOut.model_validate(euro).model_dump() == euro
    with pytest.raises(pydantic.ValidationError) as caught:
        CurrencyOut.model_validate({"currency": "JPY", "bills": []})
    assert sorted(error["loc"][0] for error in caught.value.errors()) == ["coins", "decimals"]
