"""The table app declares its module metadata, its menu, its permissions, what each role gets and its hook of the
Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, module_configs, permissions_for_role
from live.operations import registry

from apps.table import events as E
from base import home

PERMISSIONS = [
    "table.view_zone",
    "table.add_zone",
    "table.change_zone",
    "table.delete_zone",
    "table.view_table",
    "table.add_table",
    "table.change_table",
    "table.delete_table",
    "table.view_session",
    "table.add_session",
    "table.change_session",
    "table.transfer_session",
    "table.delete_session",
    "table.view_settings",
    "table.manage_settings",
]
#: Deleting zones, tables and checks and the room settings are the owner's and the admin's.
ADMIN_ONLY = {
    "table.delete_zone",
    "table.delete_table",
    "table.delete_session",
    "table.manage_settings",
}
#: The waiter (the old employee and cashier): sees the room and serves it, never draws it.
EMPLOYEE = {
    "table.view_zone",
    "table.view_table",
    "table.view_session",
    "table.add_session",
    "table.change_session",
    "table.transfer_session",
    "table.view_settings",
}


def table():
    return apps.get_app_config("table")


def test_table_is_a_live_app():
    config = table()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.table"
    assert config.label == "table"


def test_table_is_a_free_module_of_the_restaurant_group_with_a_registered_icon():
    config = table()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.RESTAURANT
    assert config.premium is False
    # Registered in the shell (ION_ICONS); the old `map-outline` waits in UI-REQUESTS.md.
    assert config.icon == "ion:grid-outline"
    assert str(config.verbose_name) == "Tables"


def test_table_requires_sale_and_customer():
    # The check of every table is an open check of Sales; its customer is Customers' link.
    assert table().requires == ["sale", "customer"]


def test_table_is_in_the_store_and_in_the_restaurant_template():
    config = table()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert table().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(table().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = table()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert (
        permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - ADMIN_ONLY
    )
    assert permissions_for_role([config], "hub_employee") == EMPLOYEE


def test_navigation_is_the_four_sections_of_the_old_module_with_registered_icons():
    # Settings is a tab of the pages (frontend/tabs.ts), shown only to whoever may save them, as the
    # old shell generated it.
    entries = table().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("floor_plan", "Floor plan", "ion:apps-outline", "/table/floor-plan"),
        ("zones", "Zones", "ion:layers-outline", "/table/zones"),
        ("tables", "Tables", "ion:grid-outline", "/table/tables"),
        ("sessions", "Sessions", "ion:time-outline", "/table/sessions"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    operations = [op for name, op in registry.items() if name.startswith("table.")]
    assert len(operations) == 36
    for op in operations:
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


def test_the_delicate_writes_are_high_risk():
    from live.operations import get

    for name in (
        "table.session.close",
        "table.session.transfer",
        "table.session.merge",
        "table.session.delete",
        "table.table.delete",
        "table.zone.delete",
    ):
        assert get(name).ai["risk"] == "high", name


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("table."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"


def test_the_expired_holds_are_swept_every_hour_as_the_system():
    # TABLE-F29: the phase-2 worker runs it on every hub; reading the plan already ignores them.
    assert table().scheduled_tasks == [
        {
            "name": "expire_table_holds",
            "operation": "table.hold.expire",
            "cron": "0 * * * *",
            "catch_up": "collapse",
        }
    ]
    from live.operations import get

    assert get("table.hold.expire").permission == "table.system"


# The Home's hook (PLAN-HUB round 2026-10-21; FIX-TABLE-SETUP-HOOKS): the old module's own item «Your tables»
# (module.json `setup`, tables#24), which reads the floor's status. The old module declared no panel and no bell row.


def test_the_homes_step_is_your_tables_done_once_one_table_is_in_use():
    """The old module's item, same order and words: recommended, as it declared it (`required: false`), done once one
    table is in use (not deleted, active: an occupied or blocked one still counts), for whoever adds tables, leading to
    the list of tables (the old `/m/tables/tables`)."""
    (step,) = table().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        dict(step.params),
        list(step.configured_when),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "tables",
        "table.floor.status",
        {},
        [SetupCheck(field="usable_tables", truthy=True)],
        "/table/tables",
        "table.add_table",
        "ion:grid-outline",
        [],
        100,
        False,
    )
    assert "usable_tables" in registry[step.operation].output.model_fields
    assert home.level_of(f"table.{step.key}", step.required) == home.LEVEL_RECOMMENDED


def test_the_step_says_the_old_words_in_the_language_of_whoever_reads_it():
    (step,) = table().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == (
        "Your tables",
        "Add the tables of your dining room: without them there is no order per table, no split and no transfer.",
    )
    assert spanish == (
        "Tus mesas",
        "Añade las mesas de tu sala: sin ellas no hay comanda por mesa, ni dividir ni transferir.",
    )


def test_the_step_is_refreshed_on_what_changes_the_tables_in_use():
    # A table added (one or many), changed (switched off or on) or deleted. Never a zone: one with tables is not
    # deleted, and a zone does not decide whether its tables are in use.
    (step,) = table().setup
    assert list(step.refresh_on) == E.TABLE_EVENTS
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


def test_the_steps_icon_is_registered():
    # The old `map-outline` waits in UI-REQUESTS.md, as the menu's.
    (step,) = table().setup
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{step.icon.removeprefix('ion:')}'" in icons


def test_tables_brings_no_panels_and_no_bell_rows_to_the_home():
    # The old module declared neither (its module.json has `widgets` and `bell` null).
    assert (table().widgets, table().bell) == ([], [])
