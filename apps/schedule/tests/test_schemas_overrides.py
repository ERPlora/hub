"""Temporary changes: their dates, their reason and how one is named."""

import datetime as dt

from apps.schedule.schemas.overrides import OverrideIn, OverridePatchIn, OverrideRefIn

from .test_schemas_fields import errors


def test_a_temporary_change_ends_on_or_after_it_starts():
    assert errors(
        OverrideIn, start_date="2026-09-01", end_date="2026-08-30", reason="x"
    ) == {"end_date": "The end date cannot be before the start date."}
    one_day = OverrideIn.model_validate(
        {"start_date": "2026-08-01", "end_date": "2026-08-01", "reason": " Inventory "}
    )
    assert (one_day.reason, one_day.is_closed) == ("Inventory", True)


def test_a_temporary_change_needs_a_reason():
    assert "reason" in errors(
        OverrideIn, start_date="2026-08-01", end_date="2026-08-15", reason="  "
    )


def test_a_temporary_change_is_named_by_id_or_by_its_reason_or_a_date_it_covers():
    assert (
        OverrideRefIn.model_validate({"override": "2026-08-10"}).override
        == "2026-08-10"
    )
    assert errors(OverrideRefIn) == {
        "override": "Say which temporary change: its id, its reason or a date it covers."
    }
    patch = OverridePatchIn.model_validate(
        {"override": "Summer", "end_date": "2026-09-15"}
    )
    assert patch.model_dump(exclude_unset=True) == {
        "override": "Summer",
        "end_date": dt.date(2026, 9, 15),
    }
