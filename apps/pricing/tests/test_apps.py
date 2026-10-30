"""The pricing app declares its module metadata, its menu entry, its permissions, what each role gets,
and the assistant's contract of every operation (``ai`` and described input fields)."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

from apps.pricing import queries, services  # noqa: F401  (importing them registers the operations)

PERMISSIONS = ["pricing.view", "pricing.manage"]
QUERIES = {
    "pricing.price_list.list",
    "pricing.price_list.get",
    "pricing.price_item.list",
    "pricing.price_item.get",
    "pricing.rule.list",
    "pricing.price.resolve",
}
COMMANDS = {
    "pricing.price_list.create",
    "pricing.price_list.update",
    "pricing.price_list.set_default",
    "pricing.price_list.deactivate",
    "pricing.price_list.activate",
    "pricing.price_item.add",
    "pricing.price_item.update",
    "pricing.price_item.remove",
    "pricing.rule.create",
    "pricing.rule.update",
    "pricing.rule.deactivate",
    "pricing.rule.activate",
    "pricing.catalog.forget_product",
    "pricing.catalog.forget_category",
    "pricing.catalog.forget_group",
    "pricing.catalog.refresh_service",
}
SYSTEM = {
    "pricing.catalog.forget_product",
    "pricing.catalog.forget_category",
    "pricing.catalog.forget_group",
    "pricing.catalog.refresh_service",
}
# What the assistant confirms before running: the general list, switching a list, removing a price,
# switching a rule off.
HIGH_RISK = {
    "pricing.price_list.set_default",
    "pricing.price_list.deactivate",
    "pricing.price_list.activate",
    "pricing.price_item.remove",
    "pricing.rule.deactivate",
}
# What an API key (erpk_live) reaches: the reads and the price sync.
EXPOSED = QUERIES | {
    "pricing.price_list.create",
    "pricing.price_list.update",
    "pricing.price_item.add",
    "pricing.price_item.update",
    "pricing.price_item.remove",
}


def pricing_app():
    return apps.get_app_config("pricing")


def pricing_operations():
    return {name: op for name, op in registry.items() if op.app_label == "pricing"}


def test_pricing_is_a_live_app_that_requires_inventory_and_customer():
    config = pricing_app()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.pricing"
    assert config.label == "pricing"
    # Products and categories are Inventory's, groups are Customers'; Services is read by name.
    assert config.requires == ["inventory", "customer"]


def test_pricing_is_a_free_module_of_the_catalog_group():
    config = pricing_app()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    assert config.icon == "ion:pricetag"
    assert str(config.verbose_name) == "Price Lists"


def test_pricing_has_the_store_metadata_and_belongs_to_both_verticals():
    config = pricing_app()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert pricing_app().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    config = pricing_app()
    assert set(config.role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == {"pricing.view"}


def test_every_granted_permission_is_declared():
    config = pricing_app()
    for granted in config.role_permissions.values():
        for permission in granted:
            assert permission == "pricing.*" or permission in config.permissions, permission


def test_navigation_is_the_one_entry_of_the_old_module_with_a_registered_icon():
    entries = pricing_app().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.icon, entry.path) for entry in entries] == [
        ("lists", "Price Lists", "ion:pricetag", "/pricing/lists"),
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app():
    operations = pricing_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in operations.items() if op.kind == "command"} == COMMANDS


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in pricing_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_the_high_risk_commands():
    assert {name for name, op in pricing_operations().items() if op.ai.get("risk") == "high"} == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    missing = [
        f"{op.name}: {field_name}"
        for op in pricing_operations().values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []


def test_what_an_api_key_reaches():
    assert {name for name, op in pricing_operations().items() if op.expose_api} == EXPOSED


def test_the_view_permission_reads_and_the_manage_permission_writes():
    for name, op in pricing_operations().items():
        if name in SYSTEM:
            continue
        assert op.permission == ("pricing.view" if op.kind == "query" else "pricing.manage"), name


def test_the_reactions_are_run_only_by_the_platform():
    # No role holds the system permission: no person and no API key reaches a reaction.
    for name in SYSTEM:
        assert registry[name].permission == "pricing.system", name
    assert "pricing.system" not in pricing_app().permissions
