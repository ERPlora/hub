"""The kitchen app declares its module metadata, its menu, its permissions and what each role gets
(WORKBOOK «Quién puede qué»)."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "kitchen.view_ticket",
    "kitchen.add_ticket",
    "kitchen.change_ticket",
    "kitchen.complete_ticket",
    "kitchen.cancel_ticket",
    "kitchen.delete_ticket",
    "kitchen.manage_station",
    "kitchen.change_settings",
    "kitchen.view_log",
]
#: The cook and the waiter only move states: no cancel, no delete, no stations, no settings.
EMPLOYEE = {
    "kitchen.view_ticket",
    "kitchen.add_ticket",
    "kitchen.change_ticket",
    "kitchen.complete_ticket",
    "kitchen.view_log",
}


def kitchen():
    return apps.get_app_config("kitchen")


def test_kitchen_is_a_live_app():
    config = kitchen()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.kitchen"
    assert config.label == "kitchen"


def test_kitchen_is_a_free_module_of_the_restaurant_group_with_a_registered_icon():
    config = kitchen()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.RESTAURANT
    assert config.premium is False
    # Registered in the shell (ION_ICONS); the old `restaurant-outline` waits in UI-REQUESTS.md.
    assert config.icon == "ion:ticket-outline"
    assert str(config.verbose_name) == "Kitchen"


def test_kitchen_requires_sale_and_inventory():
    # A ticket is a round of a check of Sales; a dish goes to the station of its product or category.
    assert kitchen().requires == ["sale", "inventory"]


def test_kitchen_is_in_the_store_and_in_the_restaurant_template():
    config = kitchen()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert kitchen().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(kitchen().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = kitchen()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == EMPLOYEE


def test_navigation_is_the_four_sections_of_the_old_module_with_registered_icons():
    entries = kitchen().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("display", "Display", "ion:desktop-outline", "/kitchen/display"),
        ("tickets", "Tickets", "ion:list-outline", "/kitchen/tickets"),
        ("stations", "Stations", "ion:layers-outline", "/kitchen/stations"),
        ("history", "History", "ion:time-outline", "/kitchen/history"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    operations = [op for name, op in registry.items() if name.startswith("kitchen.")]
    assert len(operations) == 29
    for op in operations:
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


def test_the_delicate_writes_are_high_risk():
    from live.operations import get

    for name in (
        "kitchen.ticket.cancel",
        "kitchen.ticket.delete",
        "kitchen.station.delete",
    ):
        assert get(name).ai["risk"] == "high", name


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("kitchen."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"


def test_the_reaction_to_sales_is_the_systems_only():
    # kitchen.ticket.sync runs as the system (the relay, phase 2): no role holds its permission.
    from live.operations import get

    assert get("kitchen.ticket.sync").permission == "kitchen.system"
    assert "kitchen.system" not in kitchen().permissions
