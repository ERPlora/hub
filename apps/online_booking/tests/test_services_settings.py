"""The page's settings: what changed is kept and said once, and the diary's rules are saved with them, all or
nothing."""

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.appointment.models.settings import Settings as Rules
from apps.online_booking.models import Settings
from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, QUIET, A, B, events, noted_for, received, run

pytestmark = HUB_DB


def test_saving_the_page_settings_keeps_what_changed_and_says_so(db):
    answer = run(
        "online_booking.settings.update",
        {"is_enabled": True, "page_title": "Salón Lucía"},
    )
    assert (answer.is_enabled, answer.page_title, answer.require_email) == (
        True,
        "Salón Lucía",
        False,
    )
    saved = Settings.objects.get()
    assert (saved.is_enabled, saved.page_title, saved.updated_by) == (
        True,
        "Salón Lucía",
        "tester",
    )
    assert len(events("online_booking.settings.updated")) == 1
    run("online_booking.settings.update", {"page_title": "Salón Lucía"})
    assert len(events("online_booking.settings.updated")) == 1


def test_the_rules_are_saved_in_the_diary_with_the_page_all_or_nothing(db):
    answer = run(
        "online_booking.settings.update",
        {"allow_notes": False, "min_booking_notice": 120, "auto_confirm_online": False},
    )
    assert (
        answer.allow_notes,
        answer.min_booking_notice,
        answer.auto_confirm_online,
    ) == (False, 120, False)
    rules = Rules.objects.get()
    assert (rules.min_booking_notice, rules.auto_confirm_online) == (120, False)
    assert len(events("appointment.settings.updated")) == 1
    # Without the diary's settings right, nothing of the page is saved either.
    allowed = {"online_booking.manage_settings", "appointment.view_own_appointment"}
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.settings.update",
            {"allow_notes": True, "slot_interval": 30},
            permissions=allowed,
        )
    assert Settings.objects.get().allow_notes is False
    assert Rules.objects.get().slot_interval == 15


def test_the_settings_are_the_owners_and_the_admins(db):
    with pytest.raises(PermissionDenied):
        run("online_booking.settings.update", {"is_enabled": True}, role="hub_manager")
    assert not Settings.objects.exists()


@HUB_DB_COMMITTED
def test_saving_the_settings_in_hub_b_notifies_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        run("online_booking.settings.update", {"is_enabled": True}, scope=B)
        assert noted_for() == {(B.kind, B.key)}
    assert received(on_b) == [(channel_for(B), {"events": ["online_booking.settings.updated"]})]
    assert received(on_a, timeout=QUIET) == []
    assert not OutboxEvent.objects.exists()
