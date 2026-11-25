"""Online orders' schemas: the list of the tables' codes takes pages of up to 100 and refuses a filter it does not
declare, as every list of the Hub."""

import pytest
from pydantic import ValidationError

from apps.online_order.schemas import TableCodeListIn


def test_the_list_takes_pages_of_up_to_100_tables():
    assert (TableCodeListIn().limit, TableCodeListIn().offset) == (50, 0)
    assert TableCodeListIn(limit=100, offset=200).limit == 100
    for wrong in ({"limit": 101}, {"limit": 0}, {"offset": -1}):
        with pytest.raises(ValidationError):
            TableCodeListIn.model_validate(wrong)


def test_the_list_refuses_a_filter_it_does_not_declare():
    with pytest.raises(ValidationError) as refused:
        TableCodeListIn.model_validate({"zone": "Terrace"})
    assert refused.value.errors()[0]["type"] == "extra_forbidden"
