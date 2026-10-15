"""The online booking app declares its module metadata, its menu, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

PERMISSIONS = [
    "online_booking.view_booking",
    "online_booking.change_booking",
    "online_booking.confirm_booking",
    "online_booking.delete_booking",
    "online_booking.manage_settings",
    "online_booking.public",
]
#: Deleting, the settings and previewing the public page are the owner's and the admin's.
ADMIN_ONLY = {
    "online_booking.delete_booking",
    "online_booking.manage_settings",
    "online_booking.public",
}


def online_booking():
    return apps.get_app_config("online_booking")


def test_online_booking_is_a_live_app():
    config = online_booking()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.online_booking"
    assert config.label == "online_booking"


def test_it_is_a_free_module_of_the_people_group_with_a_registered_icon():
    config = online_booking()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.PEOPLE
    assert config.premium is False
    assert config.icon == "ion:globe-outline"
    assert str(config.verbose_name) == "Online booking"


def test_it_requires_the_diary_the_customers_the_services_and_the_team():
    # The booking is an appointment of Citas; the card is Clientes'; the catalog and who does it,
    # Servicios' and Personal's.
    assert online_booking().requires == ["appointment", "customer", "service", "staff"]


def test_it_is_in_the_store_and_in_the_hair_salon_template():
    config = online_booking()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert online_booking().permissions == PERMISSIONS


def test_what_each_role_gets():
    config = online_booking()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert (
        permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - ADMIN_ONLY
    )
    assert permissions_for_role([config], "hub_employee") == {
        "online_booking.view_booking"
    }


def test_navigation_is_the_old_modules_two_entries_with_registered_icons():
    entries = online_booking().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("bookings", "Bookings", "ion:calendar-outline", "/online_booking/bookings"),
        ("settings", "Settings", "ion:settings-outline", "/online_booking/settings"),
    ]
