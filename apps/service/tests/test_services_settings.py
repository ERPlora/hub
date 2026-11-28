"""Writes of the service app's settings."""

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.service.models.settings import ServiceSettings

from .conftest import HUB_DB, events, run

pytestmark = HUB_DB


def test_the_first_save_writes_the_row_and_only_what_is_sent_changes(tax):
    out = run(
        "service.settings.update",
        {"default_duration": 45, "default_tax_category_key": tax.key},
    )
    assert (
        out.default_duration,
        out.default_buffer_time,
        out.default_tax_category_key,
    ) == (45, 0, tax.key)
    assert ServiceSettings.objects.get().updated_by == "tester"
    out = run("service.settings.update", {"show_prices": False})
    assert (out.default_duration, out.show_prices, out.default_tax_category_key) == (
        45,
        False,
        tax.key,
    )
    out = run("service.settings.update", {"default_tax_category_key": None})
    assert out.default_tax_category_key is None
    assert events() == ["service.settings.updated"] * 3
    run("service.settings.update", {"show_prices": False})
    assert len(events()) == 3


def test_a_settings_tax_category_that_does_not_exist_is_refused_under_its_field():
    with pytest.raises(InvalidPayload) as refused:
        run("service.settings.update", {"default_tax_category_key": "nope"})
    assert "default_tax_category_key" in refused.value.fields


def test_only_the_owner_and_the_admin_change_the_settings():
    with pytest.raises(PermissionDenied):
        run("service.settings.update", {"show_prices": False}, role="hub_manager")
