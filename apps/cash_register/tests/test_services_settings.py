"""The cash register's settings (CASH_REGISTER-F01), saved field by field."""

import pytest
from live.errors import PermissionDenied

from apps.cash_register.models import Settings
from apps.cash_register.tests.conftest import HUB_DB, ctx_for, events, run, settings

pytestmark = HUB_DB


# ── CASH_REGISTER-F01 Settings ──────────────────────────────────────────────────────────────────


def test_the_first_save_creates_the_row_and_keeps_the_factory_values_not_sent():
    saved = settings(require_blind_count=True)
    assert saved.require_blind_count is True
    assert saved.require_closing_balance is True
    assert saved.auto_close_time == "04:00"
    assert saved.updated_at is not None
    assert Settings.objects.count() == 1
    assert events("cash_register.settings.updated") == [
        {"fields": ["require_blind_count"]}
    ]


def test_a_save_changes_only_what_is_sent():
    settings(auto_close_enabled=True, auto_close_time="23:00")
    saved = settings(allow_negative_balance=True)
    assert (
        saved.auto_close_enabled,
        saved.auto_close_time,
        saved.allow_negative_balance,
    ) == (
        True,
        "23:00",
        True,
    )
    assert Settings.objects.get().updated_by == "tester"


def test_the_first_save_keeps_the_factory_values_as_the_businesss_and_says_so():
    """Saving the factory values as they came is the business's decision («Your cash drawer» on the Home): the row
    is born, `updated_at` with it, and the notice re-runs whoever reads the settings live."""
    saved = settings()
    assert saved.updated_at is not None
    assert Settings.objects.count() == 1
    assert events("cash_register.settings.updated") == [{"fields": []}]


def test_a_save_that_changes_nothing_says_nothing():
    settings()
    settings(require_blind_count=False)
    assert events("cash_register.settings.updated") == [{"fields": []}]


def test_only_whoever_manages_the_settings_saves_them():
    with pytest.raises(PermissionDenied):
        run(
            "cash_register.settings.update",
            {"require_blind_count": True},
            ctx_for("hub_manager"),
        )
