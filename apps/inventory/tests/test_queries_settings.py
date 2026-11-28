"""The inventory settings (``apps/inventory/queries/settings.py``): the factory ones until saved, and only for
whoever manages them."""

import pytest
from live.errors import PermissionDenied

from apps.inventory.models import Settings
from apps.inventory.schemas.settings import ConfigGetIn

from .conftest import HUB_DB, run

pytestmark = HUB_DB


def test_settings_never_saved_are_the_factory_ones():
    assert run("inventory.config.get", ConfigGetIn()).model_dump() == {
        "allow_sell_without_stock": False,
        "low_stock_threshold": 10,
        "track_stock": True,
    }


def test_saved_settings():
    Settings.objects.create(
        allow_sell_without_stock=True, low_stock_threshold=3, track_stock=False
    )
    assert run("inventory.config.get", ConfigGetIn()).model_dump() == {
        "allow_sell_without_stock": True,
        "low_stock_threshold": 3,
        "track_stock": False,
    }


def test_the_employee_does_not_see_the_settings():
    with pytest.raises(PermissionDenied):
        run("inventory.config.get", ConfigGetIn(), role="hub_employee")
