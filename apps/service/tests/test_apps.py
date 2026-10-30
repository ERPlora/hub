"""The service app declares its module metadata, its menu, its permissions, what each role gets and its hook of the
Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, module_configs, permissions_for_role
from live.operations import registry

from apps.service import events as E
from base import home

PERMISSIONS = [
    "service.view_service",
    "service.add_service",
    "service.change_service",
    "service.delete_service",
    "service.view_category",
    "service.add_category",
    "service.change_category",
    "service.delete_category",
    "service.view_package",
    "service.add_package",
    "service.change_package",
    "service.delete_package",
    "service.grant_package",
    "service.redeem_package",
    "service.view_package_balance",
    "service.view_orphan_grant",
    "service.void_grant",
    "service.adjust_grant",
    "service.return_session",
    "service.manage_settings",
]
#: Archiving, deleting and the settings are the owner's and the admin's (the old module's admin).
ADMIN_ONLY = {
    "service.delete_service",
    "service.delete_category",
    "service.delete_package",
    "service.manage_settings",
}
#: The old employee's and cashier's rights, folded into the employee.
EMPLOYEE = {
    "service.view_service",
    "service.add_service",
    "service.view_category",
    "service.view_package",
    "service.view_package_balance",
    "service.redeem_package",
    "service.grant_package",
}


def service():
    return apps.get_app_config("service")


def test_service_is_a_live_app():
    config = service()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.service"
    assert config.label == "service"


def test_service_is_a_free_module_of_the_catalog_group_with_a_registered_icon():
    config = service()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    # The old module's `briefcase`, registered in the shell (ION_ICONS).
    assert config.icon == "ion:briefcase-outline"
    assert str(config.verbose_name) == "Services"


def test_service_requires_tax_staff_and_customer():
    # The tax category of a service, the professionals who perform it, the owner of a voucher.
    assert service().requires == ["tax", "staff", "customer"]


def test_service_is_in_the_store_and_in_the_hair_salon_template():
    config = service()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert service().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(service().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    config = service()
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert (
        permissions_for_role([config], "hub_manager") == set(PERMISSIONS) - ADMIN_ONLY
    )
    assert permissions_for_role([config], "hub_employee") == EMPLOYEE


def test_navigation_is_the_three_tabs_of_the_old_module_with_registered_icons():
    entries = service().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("services", "Services", "ion:briefcase-outline", "/service/services"),
        ("categories", "Categories", "ion:pricetags-outline", "/service/categories"),
        ("packages", "Packages", "ion:gift-outline", "/service/packages"),
    ]


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    from live.operations import registry

    operations = [op for name, op in registry.items() if name.startswith("service.")]
    # 45 + the service's image (SERVICE-F34, F35): set_image, upload_image, suggest_image.
    assert len(operations) == 48
    for op in operations:
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


def test_every_input_field_says_what_it_is():
    # The assistant reads the JSON Schema of each input: a field without a description is a guess.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("service."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}: {field}"


def test_the_holds_nobody_charged_expire_every_hour_as_the_system():
    # SERVICE-F25: the worker runs it as the system; reading the balance already skips them.
    assert service().scheduled_tasks == [
        {
            "name": "expire_session_holds",
            "operation": "service.session.expire",
            "cron": "0 * * * *",
            "catch_up": "collapse",
        }
    ]
    from live.operations import get

    assert get("service.session.expire").permission == "service.system"


# The Home's hook (PLAN-HUB round 2026-10-21; FIX-SERVICE-SETUP-HOOKS): the old module's own item «Your service
# catalogue» (module.json `setup`, services#26), which reads the catalog's status. The old module declared no panel and
# no bell row.


def test_the_homes_step_is_your_service_catalogue_done_once_one_service_can_be_charged():
    """The old module's item, same order and words: functional, as it declared it (`required: true`), done once one
    offered service can be charged (its tax category alive), for whoever adds services, leading to the list of
    services (the old `/m/services/services`)."""
    (step,) = service().setup
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
        "catalog",
        "service.catalog.status",
        {},
        [SetupCheck(field="sellable_services", truthy=True)],
        "/service/services",
        "service.add_service",
        "ion:briefcase-outline",
        [],
        31,
        True,
    )
    assert "sellable_services" in registry[step.operation].output.model_fields
    assert home.level_of(f"service.{step.key}", step.required) == home.LEVEL_FUNCTIONAL


def test_the_step_says_the_old_words_in_the_language_of_whoever_reads_it():
    (step,) = service().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == ("Your service catalogue", "Add the services you sell, with their price and duration.")
    assert spanish == ("Tu catálogo de servicios", "Añade los servicios que vendes, con su precio y su duración.")


def test_the_step_is_refreshed_on_what_changes_the_services_on_offer():
    # A service added (one or many), changed (its tax category), archived or restored. Never a category or a
    # voucher: neither decides whether a service can be charged.
    (step,) = service().setup
    assert list(step.refresh_on) == E.SERVICE_EVENTS
    assert set(E.SERVICE_EVENTS) == {
        "service.service.created",
        "service.service.updated",
        "service.service.archived",
        "service.service.restored",
    }
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


def test_the_steps_icon_is_registered():
    # The app's own icon, the old module's `briefcase`.
    (step,) = service().setup
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{step.icon.removeprefix('ion:')}'" in icons


def test_services_brings_no_panels_and_no_bell_rows_to_the_home():
    # The old module declared neither (its module.json has `widgets` and `bell` null).
    assert (service().widgets, service().bell) == ([], [])
