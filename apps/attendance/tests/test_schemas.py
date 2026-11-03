"""Input and output schemas of the attendance app: what the API, the live stream and the assistant accept.

The cases come from the old module's JSON schemas (clock_in, clock_out, record_correct,
settings_update) and its batteries: a correction needs a reason of at least 3 characters and a
clock-out after its clock-in; a position is both coordinates or none; the radius is one of five.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pydantic
import pytest

from apps.attendance.schemas import (
    RECORD_SORTS,
    ClockInIn,
    ClockOutIn,
    CorrectIn,
    PageIn,
    RecordListIn,
    SettingsIn,
)

ID = uuid.uuid7()
MADRID = ZoneInfo("Europe/Madrid")


def errors_of(schema, data) -> dict[str, str]:
    with pytest.raises(pydantic.ValidationError) as caught:
        schema.model_validate(data)
    return {
        ".".join(str(p) for p in error["loc"]): error["type"]
        for error in caught.value.errors()
    }


def test_a_page_has_at_most_100_rows():
    assert PageIn().limit == 50
    assert PageIn(limit=100).limit == 100
    assert "limit" in errors_of(PageIn, {"limit": 101})
    assert "offset" in errors_of(PageIn, {"offset": -1})


def test_clocking_in_needs_nothing():
    data = ClockInIn()
    assert (data.member_id, data.member) == (None, None)
    assert (data.lat, data.lng, data.accuracy_m) == (None, None, None)


def test_clocking_in_someone_else_by_id_or_by_name():
    assert ClockInIn(member_id=ID).member_id == ID
    assert ClockInIn(member="  Ana ").member == "Ana"


def test_the_device_is_not_the_payloads_to_declare():
    # Review of 2026-10-15, finding 6: shared or personal comes from the session's device (BASE-F62).
    assert "source" not in ClockInIn.model_fields
    assert not hasattr(ClockInIn.model_validate({"source": "personal"}), "source")


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"lat": 91, "lng": 0}, "lat"),
        ({"lat": 0, "lng": 181}, "lng"),
        ({"lat": 40.4}, "lng"),
        ({"lng": -3.7}, "lng"),
        ({"lat": 40.4, "lng": -3.7, "accuracy_m": -1}, "accuracy_m"),
    ],
)
def test_a_position_is_both_coordinates_in_range(data, field):
    assert field in errors_of(ClockInIn, data)
    assert field in errors_of(ClockOutIn, data)


def test_a_position_with_its_accuracy():
    data = ClockOutIn(lat=40.4168, lng=-3.7038, accuracy_m=9.5)
    assert (data.lat, data.lng, data.accuracy_m) == (40.4168, -3.7038, 9.5)


def test_a_correction_needs_the_day_the_clock_in_and_a_reason():
    assert set(errors_of(CorrectIn, {})) == {"record_id", "clock_in_at", "reason"}


@pytest.mark.parametrize("reason", ["", "  ", "ab", " ab "])
def test_the_reason_has_at_least_3_characters(reason):
    assert "reason" in errors_of(
        CorrectIn,
        {"record_id": str(ID), "clock_in_at": "2026-10-06T08:00:00Z", "reason": reason},
    )


def test_the_reason_has_at_most_500_characters():
    data = {"record_id": str(ID), "clock_in_at": "2026-10-06T08:00:00Z"}
    assert CorrectIn(**data, reason="x" * 500).reason == "x" * 500
    assert "reason" in errors_of(CorrectIn, {**data, "reason": "x" * 501})


@pytest.mark.parametrize("out", ["2026-10-06T08:00:00Z", "2026-10-06T07:00:00Z"])
def test_the_clock_out_is_after_the_clock_in(out):
    data = {
        "record_id": str(ID),
        "clock_in_at": "2026-10-06T08:00:00Z",
        "clock_out_at": out,
        "reason": "Forgot",
    }
    assert errors_of(CorrectIn, data) == {"clock_out_at": "value_error"}


def test_a_correction_without_clock_out_reopens_the_day():
    data = CorrectIn(
        record_id=ID, clock_in_at="2026-10-06T08:00:00Z", reason="Reopen it"
    )
    assert data.clock_out_at is None


def test_times_with_any_offset_are_the_same_instant():
    # The old module refused offsets because it compared text; instants compare as instants.
    data = CorrectIn(
        record_id=ID,
        clock_in_at="2026-10-06T10:00:00+02:00",
        clock_out_at="2026-10-06T16:30:00.000Z",
        reason="Local offset",
    )
    assert data.clock_in_at == dt.datetime(2026, 10, 6, 8, tzinfo=dt.UTC)
    assert data.clock_out_at == dt.datetime(2026, 10, 6, 16, 30, tzinfo=dt.UTC)


def test_a_time_without_offset_is_the_business_wall_clock():
    # The assistant says «at nine»: the business's nine (phase 1, Europe/Madrid).
    data = CorrectIn(record_id=ID, clock_in_at="2026-10-06T09:00", reason="At nine")
    assert data.clock_in_at == dt.datetime(2026, 10, 6, 9, tzinfo=MADRID)


def test_an_impossible_date_is_refused_on_its_field():
    data = {
        "record_id": str(ID),
        "clock_in_at": "2026-02-30T08:00:00Z",
        "reason": "Bad date",
    }
    assert "clock_in_at" in errors_of(CorrectIn, data)


def test_settings_change_only_what_is_sent():
    data = SettingsIn(auto_close_after_hours=10)
    assert data.model_fields_set == {"auto_close_after_hours"}
    assert SettingsIn().model_fields_set == set()


@pytest.mark.parametrize("radius", [50, 100, 250, 500, 1000])
def test_the_five_radii(radius):
    assert SettingsIn(geofence_radius_m=radius).geofence_radius_m == radius


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"geofence_radius_m": 75}, "geofence_radius_m"),
        ({"auto_close_after_hours": 0}, "auto_close_after_hours"),
        ({"auto_close_after_hours": 25}, "auto_close_after_hours"),
        ({"auto_close_after_hours": 1.5}, "auto_close_after_hours"),
        ({"workplace_lat": 90.5}, "workplace_lat"),
        ({"workplace_lng": -180.5}, "workplace_lng"),
    ],
)
def test_the_settings_ranges(data, field):
    assert field in errors_of(SettingsIn, data)


def test_the_workplace_can_be_cleared():
    data = SettingsIn(workplace_lat=None, workplace_lng=None)
    assert data.model_fields_set == {"workplace_lat", "workplace_lng"}


def test_the_list_sorts_by_its_columns_both_ways():
    assert RecordListIn().sort == "-clock_in_at"
    for key in RECORD_SORTS:
        assert RecordListIn(sort=key).sort == key
        assert RecordListIn(sort=f"-{key}").sort == f"-{key}"
    assert "sort" in errors_of(RecordListIn, {"sort": "salary"})


def test_the_list_filters():
    data = RecordListIn(
        member_id=ID,
        status="needs_review",
        date_from="2026-10-01",
        date_to="2026-10-31",
        mine=True,
        search=" Ana ",
    )
    assert (data.member_id, data.status, data.mine, data.search) == (
        ID,
        "needs_review",
        True,
        "Ana",
    )
    assert (data.date_from, data.date_to) == (
        dt.date(2026, 10, 1),
        dt.date(2026, 10, 31),
    )
    assert "status" in errors_of(RecordListIn, {"status": "lost"})


def test_the_dates_of_a_list_are_in_order():
    assert errors_of(
        RecordListIn, {"date_from": "2026-10-31", "date_to": "2026-10-01"}
    ) == {"date_to": "value_error"}
    assert RecordListIn(
        date_from="2026-10-01", date_to="2026-10-01"
    ).date_to == dt.date(2026, 10, 1)
