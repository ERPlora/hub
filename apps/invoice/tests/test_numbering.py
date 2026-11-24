"""The year's numbering: what a request may ask of its gaps and of the numbers it gave, and what each one answers."""

import pytest
from pydantic import ValidationError

from apps.invoice.models import SERIES_CODE_MAX_LENGTH
from apps.invoice.schemas.numbering import AllocationPage, AllocationsIn, GapPage, GapsIn, NumberingStatusOut
from apps.invoice.tests.conftest import fields

LISTS = pytest.mark.parametrize("asked", [GapsIn, AllocationsIn])


@LISTS
def test_a_list_of_the_numbering_stops_at_a_hundred_rows(asked):
    with pytest.raises(ValidationError) as refused:
        asked.model_validate({"limit": 101})
    assert fields(refused.value) == {"limit"}
    assert (asked.model_validate({}).limit, asked.model_validate({}).offset) == (50, 0)


@LISTS
@pytest.mark.parametrize("year", [1999, 3000])
def test_a_year_out_of_range_is_refused(asked, year):
    with pytest.raises(ValidationError) as refused:
        asked.model_validate({"year": year})
    assert fields(refused.value) == {"year"}


@LISTS
def test_a_code_longer_than_a_series_code_is_refused(asked):
    assert asked.model_validate({"code": "X" * SERIES_CODE_MAX_LENGTH}).code == "X" * SERIES_CODE_MAX_LENGTH
    with pytest.raises(ValidationError) as refused:
        asked.model_validate({"code": "X" * (SERIES_CODE_MAX_LENGTH + 1)})
    assert fields(refused.value) == {"code"}


def test_a_page_of_gaps_carries_what_is_missing():
    gap = {
        "series_code": "FACT",
        "year": 2026,
        "after_sequence": 3,
        "missing_from": 4,
        "next_recorded": 6,
        "missing_count": 2,
    }
    page = GapPage.model_validate({"rows": [gap], "total": 1, "limit": 50, "offset": 0})
    assert page.rows[0].model_dump() == gap


def test_a_page_of_the_book_carries_the_document_of_each_number():
    number = {
        "series_code": "FACT",
        "year": 2026,
        "sequence": 12,
        "number": "FACT-2026-000012",
        "invoice_id": "01999999-0000-7000-8000-000000000000",
        "invoice_type": "F1",
        "issued_at": "2026-10-14T10:00:00Z",
    }
    page = AllocationPage.model_validate({"rows": [number], "total": 1, "limit": 50, "offset": 0})
    assert page.rows[0].model_dump(mode="json") == number


def test_the_status_says_whether_the_year_is_set_up():
    status = {
        "fiscal_year": 2026,
        "ordinary_series": 1,
        "rectifying_series": 1,
        "default_series": 1,
        "total_series": 3,
        "configured": True,
    }
    assert NumberingStatusOut.model_validate(status).model_dump() == status
    with pytest.raises(ValidationError) as refused:
        NumberingStatusOut.model_validate({key: value for key, value in status.items() if key != "configured"})
    assert fields(refused.value) == {"configured"}
