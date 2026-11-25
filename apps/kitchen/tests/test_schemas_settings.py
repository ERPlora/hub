"""The input schemas of the kitchen's settings: an edit changes only what it sends, inside its ranges and lists."""

from apps.kitchen.schemas.settings import SettingsPatchIn

from .test_schemas_fields import refuses


def test_the_settings_keep_their_ranges_and_lists():
    data = SettingsPatchIn.model_validate({"warning_minutes": 10})
    assert data.model_dump(exclude_unset=True) == {"warning_minutes": 10}
    assert refuses(SettingsPatchIn, warning_minutes=0)
    assert refuses(SettingsPatchIn, critical_minutes=121)
    assert refuses(SettingsPatchIn, sound_volume=101)
    assert refuses(SettingsPatchIn, sound_tone="siren")
    assert refuses(SettingsPatchIn, default_order_type="drive_in")
