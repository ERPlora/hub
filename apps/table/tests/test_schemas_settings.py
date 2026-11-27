"""The settings of the room: the timers of an open check."""

import pytest

from apps.table.schemas.settings import SettingsIn

from .test_schemas_fields import bad


@pytest.mark.parametrize("field", ["timer_warning_minutes", "timer_critical_minutes"])
def test_the_timers_are_one_to_six_hundred_minutes(field):
    assert bad(SettingsIn, **{field: 0})
    assert bad(SettingsIn, **{field: 601})
