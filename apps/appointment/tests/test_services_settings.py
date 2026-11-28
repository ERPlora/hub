"""The settings of the appointment app (APPOINTMENT-F19)."""

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.appointment.models.settings import Settings

from .conftest import HUB_DB, run
from .write_checks import events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_the_settings_save_only_what_is_sent_and_tell_only_a_change():
    out = run("appointment.settings.update", {"slot_interval": 30})
    assert (out.slot_interval, out.default_duration) == (30, 60)
    assert (
        Settings.objects.count() == 1
        and len(events("appointment.settings.updated")) == 1
    )
    run("appointment.settings.update", {"slot_interval": 30})
    assert len(events("appointment.settings.updated")) == 1
    run("appointment.settings.update", {"calendar_start_hour": 9})
    error = refused(
        "invalid_payload",
        lambda: run("appointment.settings.update", {"calendar_end_hour": 9}),
        InvalidPayload,
    )
    assert "calendar_end_hour" in error.fields
    with pytest.raises(PermissionDenied):
        run("appointment.settings.update", {"slot_interval": 15}, role="hub_manager")
