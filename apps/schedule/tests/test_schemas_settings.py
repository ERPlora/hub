"""The settings of the schedule app."""

from apps.schedule.schemas.settings import SettingsIn

from .test_schemas_fields import errors


def test_the_week_starts_on_monday_1_to_sunday_7():
    assert SettingsIn.model_validate({"week_starts_on": 7}).week_starts_on == 7
    assert "week_starts_on" in errors(SettingsIn, week_starts_on=0)
    assert "week_starts_on" in errors(SettingsIn, week_starts_on=8)
