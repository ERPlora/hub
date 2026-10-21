"""The inventory app declares its module metadata, its menu entry, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "inventory.view_product",
    "inventory.view_category",
    "inventory.view_stock",
    "inventory.add_product",
    "inventory.change_product",
    "inventory.delete_product",
    "inventory.add_category",
    "inventory.change_category",
    "inventory.delete_category",
    "inventory.import_product",
    "inventory.export_product",
    "inventory.adjust_stock",
    "inventory.manage_settings",
]
READ_ONLY = {"inventory.view_product", "inventory.view_category", "inventory.view_stock"}


def inventory():
    return apps.get_app_config("inventory")


def test_inventory_is_a_live_app():
    config = inventory()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.inventory"
    assert config.label == "inventory"


def test_inventory_is_a_free_module_of_the_catalog_group():
    config = inventory()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    assert config.icon == "ion:cube-outline"
    assert str(config.verbose_name) == "Inventory"


def test_inventory_requires_tax_for_the_fiscal_category_of_each_product():
    # The old manifest's depends_on: ["taxes"]; a product points at a tax.TaxCategory.
    assert inventory().requires == ["tax"]


def test_inventory_is_in_the_store_and_in_the_restaurant_template():
    # Round 16 (PLAN §21): the public store's texts. The restaurant's menu is this catalog; the hair
    # salon's template (PLAN-HUB §7, block 4) does not carry it, a salon turns it on by hand.
    config = inventory()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert inventory().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    # The old `cashier` role does not exist: what it had is what the employee has.
    assert set(inventory().role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}


def test_owner_admin_and_manager_may_do_everything_the_employee_only_reads():
    config = inventory()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == READ_ONLY


def test_navigation_opens_the_inventory_with_an_iconify_icon():
    [entry] = inventory().navigation
    assert isinstance(entry, Nav)
    assert (entry.id, str(entry.label), entry.path) == ("inventory", "Inventory", "/inventory")
    assert entry.icon == "ion:cube-outline"


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    operations = [op for name, op in registry.items() if name.startswith("inventory.")]
    assert len(operations) == 31
    for op in operations:
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name
