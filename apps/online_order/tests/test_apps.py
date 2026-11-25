"""Online orders declares its module metadata, its permissions, what each role gets and its operations."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, module_configs, permissions_for_role
from live.operations import registry

PERMISSIONS = ["online_order.view_qr_code", "online_order.change_qr_code"]


def online_order():
    return apps.get_app_config("online_order")


def test_online_order_is_a_restaurant_module_that_requires_tables():
    config = online_order()
    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("apps.online_order", "online_order", "app")
    assert config in module_configs()
    # It reads only Tables' operations today; Sales comes with Tables.
    assert config.requires == ["table"]
    assert config.category is Category.RESTAURANT
    # Sold in the store, never turned on by a template (a vertical lists only what every hub of it turns on).
    assert config.verticals == []
    assert config.premium is False
    assert config.listed is True
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    # No screen yet: the QR sheet is the next step.
    assert config.navigation == []


def test_permissions_and_roles():
    config = online_order()
    assert list(config.permissions) == PERMISSIONS
    assert set(config.role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == set()


def test_the_operations_of_the_app():
    operations = {name: op for name, op in registry.items() if name.startswith("online_order.")}
    assert {name: (op.kind, op.permission) for name, op in operations.items()} == {
        "online_order.qr_code.list": ("query", "online_order.view_qr_code"),
        "online_order.qr_code.regenerate": ("command", "online_order.change_qr_code"),
    }
    # Both are assistant tools; regenerating cannot be undone, so its card asks to type the confirmation.
    assert operations["online_order.qr_code.list"].ai_spec().risk == "normal"
    assert operations["online_order.qr_code.regenerate"].ai_spec().risk == "high"
