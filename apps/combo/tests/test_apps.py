"""The combo app declares its module metadata, its menu entry, its permissions, what each role gets and
the assistant's contract of every operation (``ai`` and described input fields)."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

from apps.combo import queries, services  # noqa: F401  (importing them registers the operations)

PERMISSIONS = ["combo.view", "combo.manage"]
QUERIES = {
    "combo.combo.list",
    "combo.combo.get",
    "combo.combo.for_sale",
    "combo.combo.resolve",
}
COMMANDS = {
    "combo.combo.create",
    "combo.combo.update",
    "combo.combo.delete",
    "combo.group.create",
    "combo.group.update",
    "combo.group.delete",
    "combo.group.reorder",
    "combo.option.create",
    "combo.option.bulk_create",
    "combo.option.update",
    "combo.option.delete",
    "combo.option.reorder",
    "combo.option.drop_product",
}
# What the assistant confirms before running: whatever deletes, and a menu's change, which may change how
# it is billed (eaten in or to take away, its VAT category): the risk is per operation, not per field.
HIGH_RISK = {
    "combo.combo.update",
    "combo.combo.delete",
    "combo.group.delete",
    "combo.option.delete",
    "combo.option.drop_product",
}


def combo_app():
    return apps.get_app_config("combo")


def combo_operations():
    return {name: op for name, op in registry.items() if op.app_label == "combo"}


def test_combo_is_a_live_app_that_requires_inventory_and_tax():
    config = combo_app()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.combo"
    assert config.label == "combo"
    # Its choices are Inventory's products; a menu eaten in has a Taxes category of its own.
    assert config.requires == ["inventory", "tax"]


def test_combo_is_a_free_module_of_the_catalog_group():
    config = combo_app()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    assert config.icon == "ion:layers-outline"
    assert str(config.verbose_name) == "Menus and combos"


def test_combo_has_the_store_metadata_and_belongs_to_the_restaurant():
    config = combo_app()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions():
    assert combo_app().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(combo_app().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_the_manager_builds_menus_and_the_employee_reads_them():
    config = combo_app()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == {"combo.view"}


def test_every_granted_permission_is_declared():
    config = combo_app()
    for granted in config.role_permissions.values():
        for permission in granted:
            assert permission == "combo.*" or permission in config.permissions, (
                permission
            )


def test_navigation_is_the_one_entry_of_the_old_module_with_a_registered_icon():
    entries = combo_app().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("menus", "Menus", "ion:layers-outline", "/combo/menus"),
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app():
    operations = combo_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in operations.items() if op.kind == "command"} == COMMANDS


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in combo_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_the_high_risk_commands():
    assert {
        name for name, op in combo_operations().items() if op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    missing = [
        f"{op.name}: {field_name}"
        for op in combo_operations().values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []


def test_every_operation_but_the_reaction_is_open_to_api_keys():
    exposed = {name for name, op in combo_operations().items() if op.expose_api}
    assert exposed == (QUERIES | COMMANDS) - {"combo.option.drop_product"}


def test_reading_needs_view_and_writing_needs_manage():
    for name, op in combo_operations().items():
        if name == "combo.option.drop_product":
            continue
        assert op.permission == (
            "combo.view" if op.kind == "query" else "combo.manage"
        ), name


def test_the_reaction_is_run_only_by_the_platform():
    # No role holds the system permission: no person and no API key reaches the reaction.
    op = registry["combo.option.drop_product"]
    assert op.permission == "combo.system"
    assert "combo.system" not in combo_app().permissions
