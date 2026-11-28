"""The cash register's settings: a cut-off that is a whole hour, and a change that saves only what it sends."""

from apps.cash_register.schemas.settings import SettingsPatchIn
from apps.cash_register.tests.schema_checks import refused


def test_the_auto_close_time_is_a_whole_hour():
    assert (
        SettingsPatchIn.model_validate({"auto_close_time": "23:00"}).auto_close_time
        == "23:00"
    )
    for wrong in ("04:30", "24:00", "4:00", ""):
        assert refused(SettingsPatchIn, auto_close_time=wrong) == ["auto_close_time"]


def test_settings_change_only_what_is_sent():
    patch = SettingsPatchIn.model_validate({"require_blind_count": True})
    assert patch.model_dump(exclude_unset=True) == {"require_blind_count": True}
