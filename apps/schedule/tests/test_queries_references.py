"""A special day or a temporary change found by id, by name or reason, or by a date (what the assistant says)."""

import uuid

import pytest
from live.errors import Conflict, NotFound

from apps.schedule.queries.references import resolve_override, resolve_special_day

from .conftest import HUB_DB, make_override, make_special_day

pytestmark = HUB_DB


def test_a_special_day_is_found_by_id_name_or_date():
    christmas = make_special_day("2026-12-25", "Christmas", recurring_yearly=True)
    make_special_day("2026-12-24", "Christmas Eve")
    assert resolve_special_day(christmas.id, None) == christmas
    assert (
        resolve_special_day(None, "christmas") == christmas
    )  # the exact name beats a part of another
    assert resolve_special_day(None, "2026-12-25") == christmas
    # A yearly one also answers for its day and month of another year.
    assert resolve_special_day(None, "2027-12-25") == christmas
    with pytest.raises(NotFound):
        resolve_special_day(None, "Easter")
    with pytest.raises(NotFound):
        resolve_special_day(uuid.uuid7(), None)


def test_a_name_that_fits_several_special_days_names_them():
    make_special_day("2026-05-01", "Local holiday A")
    make_special_day("2026-09-08", "Local holiday B")
    with pytest.raises(Conflict) as refused:
        resolve_special_day(None, "local")
    assert refused.value.code == "schedule.ambiguous_reference"
    assert (
        "Local holiday A" in refused.value.message
        and "Local holiday B" in refused.value.message
    )


def test_a_temporary_change_is_found_by_id_reason_or_a_date_it_covers():
    summer = make_override(
        "2026-07-01", "2026-08-31", "Summer hours", ("10:00", "14:00")
    )
    assert resolve_override(None, "summer") == summer
    assert resolve_override(None, "2026-08-15") == summer
    with pytest.raises(NotFound):
        resolve_override(None, "2026-09-01")
