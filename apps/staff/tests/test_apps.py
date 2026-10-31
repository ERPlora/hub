"""The staff app declares its module metadata, its menu entries, its permissions, what each role gets,
the assistant's contract of every operation (``ai`` and described input fields) and its panels of the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, Widget, module_configs, permissions_for_role
from live.operations import INTERNAL, registry

from apps.staff import events as E
from apps.staff import queries, services  # noqa: F401  (importing them registers the operations)

# The old module's permissions, one by one (module.json), plus asking for one's own time off.
PERMISSIONS = [
    "staff.view",
    "staff.view_compensation",
    "staff.add_member",
    "staff.change_member",
    "staff.delete_member",
    "staff.view_time_off",
    "staff.view_time_off_detail",
    "staff.manage_time_off",
    "staff.manage_settings",
    "staff.request_time_off",
]
QUERIES = {
    "staff.member.list",
    "staff.member.detail",
    "staff.member.mine",
    "staff.member.current",
    "staff.member.compensation",
    "staff.member.stats",
    "staff.commission.summary",
    "staff.commission.report",
    "staff.role.list",
    "staff.role.resolve",
    "staff.schedule.list",
    "staff.schedule.detail",
    "staff.availability.for_member",
    "staff.time_off.list",
    "staff.time_off.detail",
    "staff.time_off.today",
    "staff.time_off.mine",
    "staff.settings.get",
    "staff.account.list",
}
COMMANDS = {
    "staff.member.create",
    "staff.member.bulk_create",
    "staff.member.update",
    "staff.member.deactivate",
    "staff.member.terminate",
    "staff.role.create",
    "staff.role.update",
    "staff.schedule.create",
    "staff.schedule.update",
    "staff.schedule.set_active",
    "staff.schedule.delete",
    "staff.time_off.create",
    "staff.time_off.request",
    "staff.time_off.approve",
    "staff.time_off.reject",
    "staff.time_off.cancel",
    "staff.settings.update",
}
# What the assistant confirms before running: a termination, a deletion, a change of pay.
HIGH_RISK = {
    "staff.member.update",
    "staff.member.deactivate",
    "staff.member.terminate",
    "staff.schedule.delete",
}


def staff():
    return apps.get_app_config("staff")


def staff_operations():
    return {name: op for name, op in registry.items() if op.app_label == "staff"}


def test_staff_is_a_live_app():
    config = staff()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.staff"
    assert config.requires == []


def test_staff_is_a_free_module_of_the_people_group():
    config = staff()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:id-card-outline"
    assert str(config.verbose_name) == "Staff"


def test_staff_has_the_store_metadata_and_belongs_to_the_hair_salon():
    # Round 16 (PLAN §21): a hair salon needs its team from sign-up; a restaurant may go without it.
    config = staff()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["hair_salon"]
    assert config.listed is True


def test_permissions():
    assert staff().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    # There is no cashier any more: the old cashier's directory view is the employee's.
    assert set(staff().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_roles():
    config = staff()
    assert permissions_for_role([config], "hub_owner") == set(PERMISSIONS)
    assert permissions_for_role([config], "hub_admin") == set(PERMISSIONS)
    # Only the owner and the admin deactivate or terminate (the old module's admin-only permission).
    assert permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - {
        "staff.delete_member"
    }
    # An employee sees the team and who is away, and asks for their own time off.
    assert permissions_for_role([config], "hub_employee") == {
        "staff.view",
        "staff.view_time_off",
        "staff.request_time_off",
    }


def test_every_granted_permission_is_declared():
    config = staff()
    for granted in config.role_permissions.values():
        for permission in granted:
            assert permission == "staff.*" or permission in config.permissions, (
                permission
            )


def test_navigation_is_the_four_tabs_of_the_old_module():
    entries = staff().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("staff", "Staff", "/staff/members", "ion:people-outline"),
        ("roles", "Roles", "/staff/roles", "ion:shield-outline"),
        ("time_off", "Time Off", "/staff/time-off", "ion:calendar-outline"),
        ("schedules", "Schedules", "/staff/schedules", "ion:time-outline"),
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app():
    operations = staff_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in operations.items() if op.kind == "command"} == COMMANDS


#: The reads that are no assistant tool: the check of a new member's role before its card (hub#538).
INTERNAL_READS = {"staff.role.resolve"}


def test_every_operation_tells_the_assistant_what_it_does():
    operations = staff_operations()
    assert {name for name, op in operations.items() if op.ai is INTERNAL} == INTERNAL_READS
    for name, op in operations.items():
        if name in INTERNAL_READS:
            continue
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name


def test_the_high_risk_commands():
    assert {
        name
        for name, op in staff_operations().items()
        if isinstance(op.ai, dict) and op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    missing = [
        f"{op.name}: {field_name}"
        for op in staff_operations().values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []


# The Home's panels (PLAN-HUB round 2026-10-21; FIX-STAFF-SETUP-HOOKS): the old module's module.json `widgets` (it had
# no `setup` nor `bell`), on the queries Staff's own figures already read (STAFF-F20, STAFF-F23).

PANELS = ["headcount", "on_leave_today", "pending_time_off", "time_off_today", "by_role"]
#: What re-runs each query, as live.py says it: the panel follows the screen that reads the same figures.
FIGURES = [*E.MEMBER_ALL, *E.TIME_OFF_ALL]
AWAY_TODAY = [E.TIME_OFF_APPROVED, E.TIME_OFF_CANCELLED, E.MEMBER_UPDATED, E.MEMBER_TERMINATED]
BY_ROLE = [*E.ROLE_ALL, *E.MEMBER_ALL]


def test_the_homes_panels_are_the_old_modules_five():
    """The head count, who is away today and today's time off on by default; the requests to answer and the people by
    role to add. Who sees the team reads the head count and the roles; who sees the time off, the rest."""
    panels = staff().widgets
    assert all(isinstance(panel, Widget) for panel in panels)
    assert [
        (
            panel.key,
            panel.kind,
            panel.component,
            panel.operation,
            panel.size,
            panel.default,
            panel.permission,
            dict(panel.params),
            dict(panel.map),
            dict(panel.options),
        )
        for panel in panels
    ] == [
        ("headcount", "kpi", None, "staff.member.stats", "sm", True, "staff.view", {}, {"value": "active"}, {"format": "number"}),
        (
            "on_leave_today",
            "stat",
            None,
            "staff.member.stats",
            "sm",
            True,
            "staff.view_time_off",
            {},
            {"value": "absent_today"},
            {"format": "number"},
        ),
        (
            "pending_time_off",
            "kpi",
            None,
            "staff.member.stats",
            "sm",
            False,
            "staff.view_time_off",
            {},
            {"value": "pending_time_off"},
            {"format": "number"},
        ),
        (
            "time_off_today",
            "timeline",
            None,
            "staff.time_off.today",
            "md",
            True,
            "staff.view_time_off",
            {},
            {"title": "member_name", "description": "leave_type_label"},
            {},
        ),
        (
            "by_role",
            "bar-list",
            None,
            "staff.role.list",
            "md",
            False,
            "staff.view",
            {"sort": "-member_count", "limit": 10},
            # Each bar in its role's colour, as the old module's `map.color` (FIX-HUB-STAFF-ROLE-BARS-IGNORE-ROLE-COLOR).
            {"label": "name", "value": "member_count", "color": "color"},
            {"valueFormat": "number"},
        ),
    ]
    # Every business with Staff on (the old sectors were all of them), grouped under the app's own name.
    assert all(not panel.verticals and not panel.category for panel in panels)


def test_each_panel_maps_fields_its_query_gives_and_takes_its_params():
    """A map that names no field of the query leaves the panel blank without an error (the maintenance note of
    STAFF-F23): every field it reads is one the query's output has."""
    for panel in staff().widgets:
        output = registry[panel.operation].output.model_fields
        if "rows" in output:
            output = output["rows"].annotation.__args__[0].model_fields
        assert set(panel.map.values()) <= set(output), panel.key
        registry[panel.operation].input.model_validate(dict(panel.params))


def test_a_kpi_says_its_name_once():
    # gh:hub#1105: the old KPIs painted their header twice (the title and options.label with its icon).
    for panel in staff().widgets:
        if panel.kind in {"kpi", "stat"}:
            assert not {"label", "icon"} & set(panel.options), panel.key


def test_the_panels_are_titled_in_english_and_in_spanish():
    with translation.override("en"):
        english = [str(panel.title) for panel in staff().widgets]
    with translation.override("es"):
        spanish = [str(panel.title) for panel in staff().widgets]
    assert english == ["Active staff", "On leave today", "Pending time off", "Today’s time off", "Staff by role"]
    assert spanish == ["Plantilla activa", "Ausentes hoy", "Ausencias pendientes", "Ausencias de hoy", "Empleados por rol"]


def test_each_panel_is_refreshed_by_the_events_that_re_run_its_query():
    panels = {panel.key: panel for panel in staff().widgets}
    assert list(panels) == PANELS
    expected = {
        "headcount": FIGURES,
        "on_leave_today": FIGURES,
        "pending_time_off": FIGURES,
        "time_off_today": AWAY_TODAY,
        "by_role": BY_ROLE,
    }
    for key, panel in panels.items():
        assert list(panel.refresh_on) == expected[key], key
        assert live_registry.is_subscribable(panel.operation), key
        assert set(panel.refresh_on) == set(live_registry.subscribable[panel.operation]), key


def test_the_panels_icons_are_registered_in_the_shell():
    # The old airplane and hourglass are not registered: UI-REQUESTS.md asks for them.
    icons = [panel.icon for panel in staff().widgets]
    assert icons == ["ion:people-outline", "ion:log-out-outline", "ion:time-outline", "ion:calendar-outline", "ion:shield-outline"]
    shell = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in icons:
        assert f"'{icon.removeprefix('ion:')}':" in shell, icon


def test_staff_has_no_setup_steps_nor_bell_counters():
    # The old module declared none (its module.json has no `setup` nor `bell`).
    assert staff().setup == []
    assert staff().bell == []
