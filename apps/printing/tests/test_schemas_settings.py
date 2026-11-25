"""Schemas of the printing settings: what their patch accepts and what it refuses."""

from apps.printing.schemas.settings import SettingsPatchIn

from .test_schemas_fields import refused


def test_the_settings_patch_takes_copies_up_to_3():
    refused(SettingsPatchIn, {"receipt_copies": 4})
    patch = SettingsPatchIn.model_validate({"kitchen_printer": None})
    assert patch.model_dump(exclude_unset=True) == {"kitchen_printer": None}
