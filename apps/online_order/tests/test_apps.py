"""Online orders declares its module metadata, its permissions, what each role gets and its operations."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, module_configs, permissions_for_role
from live.operations import registry

PERMISSIONS = ["online_order.view_qr_code", "online_order.change_qr_code", "online_order.public"]
#: What the manager holds: the codes, never the public page's permission, which only the owner and the admin hold.
MANAGER = {"online_order.view_qr_code", "online_order.change_qr_code"}


def online_order():
    return apps.get_app_config("online_order")


def test_online_order_is_a_restaurant_module_that_requires_tables_and_inventory():
    config = online_order()
    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("apps.online_order", "online_order", "app")
    assert config in module_configs()
    # It reads Tables' operations and the menu by Inventory's; Sales comes with Tables.
    assert config.requires == ["table", "inventory"]
    assert config.category is Category.RESTAURANT
    # Never turned on by a template (a vertical lists only what every hub of it turns on).
    assert config.verticals == []
    assert config.premium is False
    # Out of the store until the customer can order: a printed QR must not open a page that does not exist yet.
    assert config.listed is False
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    # One screen, the tables' QR codes, for whoever may see them.
    assert [(nav.id, str(nav.label), nav.icon, nav.path, nav.permission) for nav in config.navigation] == [
        ("qr_codes", "QR codes", "ion:qr-code-outline", "/online_order/qr-codes", "online_order.view_qr_code"),
    ]


def test_permissions_and_roles():
    config = online_order()
    assert list(config.permissions) == PERMISSIONS
    assert set(config.role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_manager") == MANAGER
    assert permissions_for_role([config], "hub_employee") == set()


def test_the_operations_of_the_app():
    operations = {name: op for name, op in registry.items() if name.startswith("online_order.")}
    assert {name: (op.kind, op.permission) for name, op in operations.items()} == {
        "online_order.qr_code.list": ("query", "online_order.view_qr_code"),
        "online_order.qr_code.regenerate": ("command", "online_order.change_qr_code"),
        "online_order.public.menu": ("query", "online_order.public"),
        "online_order.public.options": ("query", "online_order.public"),
    }
    # Both are assistant tools; regenerating cannot be undone, so its card asks to type the confirmation.
    assert operations["online_order.qr_code.list"].ai_spec().risk == "normal"
    assert operations["online_order.qr_code.regenerate"].ai_spec().risk == "high"
    # The table's page reads are the customer's, not the team's assistant's tools.
    assert not operations["online_order.public.menu"].ai and not operations["online_order.public.options"].ai


def test_its_table_page_is_served_by_base_s_public_door():
    assert online_order().public_pages == {"order": "online_order.public"}
