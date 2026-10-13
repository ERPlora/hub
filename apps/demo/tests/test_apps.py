"""The demo app declares its module metadata, its menu entry, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role


def demo():
    return apps.get_app_config("demo")


def test_demo_is_a_live_app():
    config = demo()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.demo"
    assert config.requires == []


def test_demo_is_a_free_module_of_the_organization_group():
    config = demo()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    # The same icon as its menu entry, with its Iconify set prefix.
    assert config.icon == "ion:flask-outline"
    # The apps page shows icon and name only (Ioan, 2026-10-13).
    assert not hasattr(config, "description")


def test_permissions():
    assert demo().permissions == ["demo.view", "demo.manage"]


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(demo().role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}


def test_roles():
    config = demo()
    assert permissions_for_role([config], "hub_owner") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_admin") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_manager") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_employee") == {"demo.view"}


def test_navigation_points_at_the_item_list_with_an_iconify_icon():
    [entry] = demo().navigation
    assert isinstance(entry, Nav)
    assert (entry.id, str(entry.label), entry.path) == ("demo", "Demo", "/demo/items")
    # Iconify names carry their set prefix (HubIcon, working-rules §11).
    assert entry.icon == "ion:flask-outline"
