"""Input schemas of the schedule app: what the API, the live stream and the assistant accept, and the 422 per field
of what they refuse (``errors``, which the tests of every schema module read). Here, the lists and their page."""

import pydantic
import pytest
from live.ninja import _field_message

from apps.schedule.schemas.fields import PageIn
from apps.schedule.schemas.overrides import OverrideListIn
from apps.schedule.schemas.special_days import SpecialDayListIn


def errors(schema, **data) -> dict[str, str]:
    """``field → message`` of the validation errors, as the 422's ``fields`` gives them."""
    with pytest.raises(pydantic.ValidationError) as refused:
        schema.model_validate(data)
    return {
        ".".join(str(part) for part in error["loc"]): _field_message(error)
        for error in refused.value.errors()
    }


def test_a_page_is_at_most_100_rows():
    assert PageIn().limit == 50
    assert "limit" in errors(SpecialDayListIn, limit=101)
    assert "limit" in errors(OverrideListIn, limit=0)


def test_a_filter_not_declared_is_refused():
    assert errors(SpecialDayListIn, colour="red") == {
        "colour": "This field is not allowed."
    }
    assert "colour" in errors(OverrideListIn, colour="red")


def test_the_lists_sort_by_date_by_default():
    assert (SpecialDayListIn().sort, SpecialDayListIn().dir) == ("date", "asc")
    assert OverrideListIn().sort == "start_date"
    assert "sort" in errors(SpecialDayListIn, sort="notes")


def test_a_date_range_filter_backwards_is_refused():
    assert "date_to" in errors(
        SpecialDayListIn, date_from="2026-12-31", date_to="2026-01-01"
    )
