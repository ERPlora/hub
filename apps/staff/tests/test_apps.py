"""The staff app declares its module metadata, its menu entries, its permissions, what each role gets,
and the assistant's contract of every operation (``ai`` and described input fields)."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

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


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in staff_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name


def test_the_high_risk_commands():
    assert {
        name for name, op in staff_operations().items() if op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    missing = [
        f"{op.name}: {field_name}"
        for op in staff_operations().values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []
