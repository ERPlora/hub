"""Input and output schemas of the schedule app: what the API, the live stream and the assistant accept.

The rules of a set of intervals are the old handler's (schedules#8, #23, #28): one code, one meaning,
whichever form sends them. Each refusal lands under its field (the 422's ``fields``).
"""

import datetime as dt
import uuid

import pydantic
import pytest
from django.utils import translation
from live.ninja import _field_message

from apps.schedule.schemas import (
    BulkSpecialDayIn,
    HoursRangeIn,
    IntervalIn,
    IsOpenIn,
    OverrideIn,
    OverrideListIn,
    OverridePatchIn,
    OverrideRefIn,
    PageIn,
    SetDayIn,
    SettingsIn,
    SpecialDayIn,
    SpecialDayListIn,
    SpecialDayPatchIn,
    SpecialDayRefIn,
    check_intervals,
)


def errors(schema, **data) -> dict[str, str]:
    """``field → message`` of the validation errors, as the 422's ``fields`` gives them."""
    with pytest.raises(pydantic.ValidationError) as refused:
        schema.model_validate(data)
    return {
        ".".join(str(part) for part in error["loc"]): _field_message(error)
        for error in refused.value.errors()
    }


def hours(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"open_time": start, "close_time": end} for start, end in pairs]


# ── A weekday, by number or by name ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "weekday"),
    [
        (0, 0),
        ("6", 6),
        ("monday", 0),
        ("Lunes", 0),
        ("miércoles", 2),
        ("miercoles", 2),
        ("Sun", 6),
        ("sábado", 5),
        ("el lunes", 0),
        ("El Sábado", 5),
        ("the sunday", 6),
    ],
)
def test_a_weekday_is_a_number_or_its_name_in_english_or_spanish(value, weekday):
    assert (
        SetDayIn.model_validate({"weekday": value, "is_closed": True}).weekday
        == weekday
    )


@pytest.mark.parametrize("value", [7, -1, "someday", ""])
def test_a_weekday_out_of_the_week_is_refused(value):
    assert "weekday" in errors(SetDayIn, weekday=value, is_closed=True)


# ── The intervals of a day ─────────────────────────────────────────────────────────────────────


def test_an_open_day_takes_its_intervals_sorted():
    day = SetDayIn.model_validate(
        {"weekday": 1, "intervals": hours(("17:00", "20:00"), ("10:00", "14:00"))}
    )
    assert [(i.open_time, i.close_time) for i in day.intervals] == [
        (dt.time(10), dt.time(14)),
        (dt.time(17), dt.time(20)),
    ]
    assert day.is_closed is False


def test_a_closed_day_drops_its_intervals():
    day = SetDayIn.model_validate(
        {"weekday": 6, "is_closed": True, "intervals": hours(("10:00", "14:00"))}
    )
    assert day.intervals == []


@pytest.mark.parametrize(
    ("intervals", "message"),
    [
        ([], "An open day needs at least one opening interval."),
        (
            hours(("10:00", "10:00")),
            "An interval cannot open and close at the same time; 00:00–00:00 is open 24 hours.",
        ),
        (
            hours(("09:00", "14:00"), ("13:00", "18:00")),
            "Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash.",
        ),
    ],
)
def test_the_rules_of_the_intervals_land_under_intervals(intervals, message):
    assert errors(SetDayIn, weekday=0, intervals=intervals) == {"intervals": message}
    assert errors(
        SpecialDayIn,
        date="2026-12-24",
        name="Eve",
        is_closed=False,
        intervals=intervals,
    ) == {"intervals": message}
    assert errors(
        OverrideIn,
        start_date="2026-08-01",
        end_date="2026-08-31",
        reason="Summer",
        is_closed=False,
        intervals=intervals,
    ) == {"intervals": message}


def test_at_most_twelve_intervals():
    thirteen = hours(*[(f"{hour:02d}:00", f"{hour:02d}:30") for hour in range(13)])
    assert "intervals" in errors(SetDayIn, weekday=0, intervals=thirteen)


def test_overnight_and_24_hours_are_intervals_too():
    assert SetDayIn.model_validate(
        {"weekday": 4, "intervals": hours(("22:00", "02:00"))}
    ).intervals[0].close_time == dt.time(2)
    assert SetDayIn.model_validate(
        {"weekday": 5, "intervals": hours(("00:00", "00:00"))}
    ).intervals[0].open_time == dt.time(0)


def test_a_time_that_is_not_a_time_is_refused_under_its_field():
    assert "intervals.0.open_time" in errors(
        SetDayIn, weekday=0, intervals=hours(("25:00", "18:00"))
    )


def test_check_intervals_is_the_one_rule_for_every_form():
    assert (
        check_intervals(
            True, [IntervalIn(open_time=dt.time(9), close_time=dt.time(10))]
        )
        == []
    )
    with pytest.raises(ValueError, match="An open day needs"):
        check_intervals(False, [])


def test_the_messages_speak_spanish():
    with translation.override("es"):
        assert errors(SetDayIn, weekday=0, intervals=[]) == {
            "intervals": "Un día abierto necesita al menos un tramo horario."
        }


# ── Special days ───────────────────────────────────────────────────────────────────────────────


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


# ── Temporary changes ──────────────────────────────────────────────────────────────────────────


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


# ── Lists ──────────────────────────────────────────────────────────────────────────────────────


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


# ── Settings, is it open, hours of a range ─────────────────────────────────────────────────────


def test_the_week_starts_on_monday_1_to_sunday_7():
    assert SettingsIn.model_validate({"week_starts_on": 7}).week_starts_on == 7
    assert "week_starts_on" in errors(SettingsIn, week_starts_on=0)
    assert "week_starts_on" in errors(SettingsIn, week_starts_on=8)


def test_is_open_takes_the_moment_and_nothing_else():
    assert IsOpenIn().when is None
    assert (
        IsOpenIn.model_validate({"when": "2026-08-18T10:00"}).when == "2026-08-18T10:00"
    )
    # The rules are read from the server, never from the caller (schedules#1).
    assert "business_hours" in errors(IsOpenIn, business_hours=[])


def test_the_hours_of_a_range_take_up_to_366_days_and_one_day_alone():
    one = HoursRangeIn.model_validate({"date_from": "2026-08-17"})
    assert one.date_to == dt.date(2026, 8, 17)
    HoursRangeIn.model_validate({"date_from": "2026-01-01", "date_to": "2027-01-01"})
    assert errors(HoursRangeIn, date_from="2026-01-01", date_to="2027-01-02") == {
        "date_to": "At most 366 days at once."
    }
    assert errors(HoursRangeIn, date_from="2026-08-17", date_to="2026-08-16") == {
        "date_to": "The end date cannot be before the start date."
    }


# ── The ends of the calendar: a 422 under the field, never a 500 (review of 2026-10-14) ────────


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"date_from": "0001-01-01"}, "date_from"),
        ({"date_from": "1899-12-31"}, "date_from"),
        ({"date_from": "2200-12-31", "date_to": "9999-12-31"}, "date_to"),
        ({"date_from": "9999-12-31"}, "date_from"),
    ],
)
def test_the_hours_of_a_range_stay_between_1900_and_2200(data, field):
    assert errors(HoursRangeIn, **data) == {field: "Choose a date between 1900 and 2200."}


def test_the_first_and_last_days_of_the_range_are_fine():
    HoursRangeIn.model_validate({"date_from": "1900-01-01"})
    HoursRangeIn.model_validate({"date_from": "2200-12-31"})


@pytest.mark.parametrize(
    "when",
    ["0001-01-01T10:00", "0001-01-01T00:30+01:00", "9999-12-31T23:30-01:00", "9999-12-31T23:30+00:00", "1899-12-31T10:00"],
)
def test_is_open_refuses_a_moment_out_of_the_calendar_under_when(when):
    assert errors(IsOpenIn, when=when) == {"when": "Choose a date between 1900 and 2200."}
