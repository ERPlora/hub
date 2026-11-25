"""Special days: one, a bulk of them, and how a special day is named."""

import uuid

from apps.schedule.schemas.special_days import (
    BulkSpecialDayIn,
    SpecialDayIn,
    SpecialDayPatchIn,
    SpecialDayRefIn,
)

from .test_schemas_fields import errors


def test_a_special_day_is_closed_and_not_yearly_unless_told():
    christmas = SpecialDayIn.model_validate(
        {"date": "2026-12-25", "name": "  Christmas  "}
    )
    assert (
        christmas.name,
        christmas.is_closed,
        christmas.recurring_yearly,
        christmas.notes,
        christmas.intervals,
    ) == (
        "Christmas",
        True,
        False,
        "",
        [],
    )


def test_a_special_day_needs_a_real_date_and_a_name():
    assert "date" in errors(SpecialDayIn, date="2026-02-31", name="Nope")
    assert "name" in errors(SpecialDayIn, date="2026-12-25", name="   ")
    assert "name" in errors(SpecialDayIn, date="2026-12-25", name="x" * 201)


def test_a_special_day_is_named_by_id_or_by_its_name_or_date():
    assert SpecialDayRefIn.model_validate({"id": str(uuid.uuid7())}).special_day is None
    assert (
        SpecialDayRefIn.model_validate({"special_day": "Christmas"}).special_day
        == "Christmas"
    )
    assert errors(SpecialDayRefIn) == {
        "special_day": "Say which special day: its id, its name or its date."
    }


def test_a_special_day_patch_changes_only_what_is_sent():
    patch = SpecialDayPatchIn.model_validate(
        {"special_day": "Christmas", "notes": "Family"}
    )
    assert patch.model_dump(exclude_unset=True) == {
        "special_day": "Christmas",
        "notes": "Family",
    }


def test_the_bulk_takes_one_to_366_days():
    assert errors(BulkSpecialDayIn, special_days=[]) == {
        "special_days": "Ensure this value has at least 1 item."
    }
    day = {"date": "2026-01-01", "name": "New Year"}
    assert "special_days" in errors(BulkSpecialDayIn, special_days=[day] * 367)
    assert (
        len(BulkSpecialDayIn.model_validate({"special_days": [day] * 366}).special_days)
        == 366
    )


def test_the_bulk_leaves_the_rules_of_the_intervals_to_each_day():
    # A day with bad hours is skipped with its reason by the service; the list still validates.
    bulk = BulkSpecialDayIn.model_validate(
        {
            "special_days": [
                {
                    "date": "2026-12-24",
                    "name": "Eve",
                    "is_closed": False,
                    "intervals": [],
                }
            ]
        }
    )
    assert bulk.special_days[0].is_closed is False


def test_the_bulk_refuses_a_day_without_a_real_date_or_a_name():
    assert "special_days.0.date" in errors(
        BulkSpecialDayIn, special_days=[{"date": "2026-02-31", "name": "Nope"}]
    )
    assert "special_days.0.name" in errors(
        BulkSpecialDayIn, special_days=[{"date": "2026-02-28"}]
    )
