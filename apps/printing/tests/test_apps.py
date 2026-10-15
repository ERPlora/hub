"""The printing app declares its module metadata, its menu, its permissions and what each role gets."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, module_configs, permissions_for_role

PERMISSIONS = [
    "printing.view_settings",
    "printing.manage_settings",
    "printing.print",
    "printing.manage_jobs",
]


def config():
    return apps.get_app_config("printing")


def test_it_is_an_installed_live_app():
    assert isinstance(config(), LiveAppConfig)
    assert config().name == "apps.printing"
    assert "apps.printing" in settings.INSTALLED_APPS


def test_it_requires_nothing():
    # Every app that prints calls printing.job.create by name and sends its document composed.
    assert config().requires == []


def test_it_is_a_free_module_of_the_organization_group_with_a_registered_icon():
    assert config().kind == "app"
    assert config() in module_configs()
    assert config().category is Category.ORGANIZATION
    assert config().premium is False
    # `ion:print-outline` is not registered in the shell yet (UI-REQUESTS.md): lucide's receipt stands in.
    assert config().icon == "lucide:receipt"
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in [config().icon, *(entry.icon for entry in config().navigation)]:
        name = icon.removeprefix("ion:")
        assert f"'{name}'" in icons, icon


def test_it_is_in_the_store_and_in_both_verticals():
    assert 0 < len(str(config().summary)) <= 120
    assert str(config().description)
    assert config().verticals == ["hair_salon", "restaurant"]
    assert config().listed is True


def test_permissions():
    assert config().permissions == PERMISSIONS


def test_what_each_role_gets():
    configs = [config()]
    assert permissions_for_role(configs, "hub_owner") == frozenset(PERMISSIONS)
    assert permissions_for_role(configs, "hub_admin") == frozenset(PERMISSIONS)
    # The manager sets printers up; the queue's retry and cancel stay with whoever runs the business.
    assert permissions_for_role(configs, "hub_manager") == frozenset(
        {"printing.view_settings", "printing.manage_settings", "printing.print"}
    )
    assert permissions_for_role(configs, "hub_employee") == frozenset({"printing.view_settings", "printing.print"})


def test_the_menu_is_its_three_tabs():
    assert [(nav.id, str(nav.label), nav.icon, nav.path) for nav in config().navigation] == [
        ("printers", "Printers", "lucide:receipt", "/printing/printers"),
        ("jobs", "Queue", "ion:list-outline", "/printing/jobs"),
        ("settings", "Settings", "ion:settings-outline", "/printing/settings"),
    ]


def test_no_scheduled_task():
    assert getattr(config(), "scheduled_tasks", []) == []
