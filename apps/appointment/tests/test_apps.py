"""The appointment app declares its module metadata, its menu, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "appointment.view_appointment",
    "appointment.view_own_appointment",
    "appointment.add_appointment",
    "appointment.add_own_appointment",
    "appointment.change_appointment",
    "appointment.change_own_appointment",
    "appointment.delete_appointment",
    "appointment.view_schedule",
    "appointment.manage_schedule",
    "appointment.manage_settings",
]
#: Deleting and the settings are the owner's and the admin's (the old module's admin).
ADMIN_ONLY = {"appointment.delete_appointment", "appointment.manage_settings"}
#: The employee sees and manages their own agenda (WORKBOOK «Quién puede qué»).
EMPLOYEE = {
    "appointment.view_own_appointment",
    "appointment.add_own_appointment",
    "appointment.change_own_appointment",
    "appointment.view_schedule",
}


def appointment():
    return apps.get_app_config("appointment")


def test_appointment_is_a_live_app():
    config = appointment()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.appointment"
    assert config.label == "appointment"


def test_appointment_is_a_free_module_of_the_people_group_with_a_registered_icon():
    config = appointment()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:calendar-outline"
    assert str(config.verbose_name) == "Appointments"


def test_appointment_requires_customer_service_staff_and_schedule():
    # The customer of an appointment, its services, its professional and the business's hours.
    assert appointment().requires == ["customer", "service", "staff", "schedule"]


def test_appointment_is_in_the_store_and_in_the_hair_salon_template():
    config = appointment()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert appointment().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(appointment().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = appointment()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert (
        permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - ADMIN_ONLY
    )
    assert permissions_for_role([config], "hub_employee") == EMPLOYEE


def test_navigation_is_the_old_modules_single_entry_with_a_registered_icon():
    entries = appointment().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("appointments", "Appointments", "ion:calendar-outline", "/appointment/agenda"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("appointment.")}
    assert ops, "the appointment app declares no operation"
    for name, op in ops.items():
        assert op.ai and op.ai.get("description"), name
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name


def test_cancelling_marking_a_no_show_charging_and_deleting_are_high_risk():
    from live.operations import get

    for name in (
        "appointment.appointment.cancel",
        "appointment.appointment.mark_no_show",
        "appointment.appointment.charge",
        "appointment.appointment.delete",
        "appointment.appointment.bulk_delete",
        "appointment.recurring.delete",
        "appointment.blocked_time.delete",
    ):
        assert get(name).ai["risk"] == "high", name
