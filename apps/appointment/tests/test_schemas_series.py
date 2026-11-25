"""A repeating appointment has a rule."""

from apps.appointment.schemas.series import RecurringCreateIn, RecurringUpdateIn

from .schema_checks import ID, MONDAY, errors


def test_a_series_has_a_rule_and_its_end_is_not_before_its_start():
    series = {
        "customer": "Lucía",
        "services": [{"service": "Cut"}],
        "staff": "Ana",
        "frequency": "weekly",
        "start_date": MONDAY,
        "time": "10:00",
    }
    assert not errors(RecurringCreateIn, **series)
    assert "frequency" in errors(RecurringCreateIn, **{**series, "frequency": "yearly"})
    assert "day_of_week" in errors(RecurringCreateIn, **{**series, "day_of_week": 7})
    assert "end_date" in errors(
        RecurringCreateIn, **{**series, "end_date": "2026-10-01"}
    )
    assert "max_occurrences" in errors(
        RecurringCreateIn, **{**series, "max_occurrences": 0}
    )
    assert "__all__" in errors(RecurringUpdateIn, id=ID, from_date=MONDAY)
    assert not errors(RecurringUpdateIn, id=ID, from_date=MONDAY, time="11:00")
