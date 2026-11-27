"""The service app declares its module metadata, its menu, its permissions, what each role gets and its hook of the
Home."""

import pytest
from django.apps import apps
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, module_configs
from live.operations import registry

from apps.service import events as E
from base import home
from base.tenancy.tests.business import HUB_DB
from base.tests import help_videos
from base.tests.roles import grants_by_role
from base.tests.shell_icons import shell_icon_registry

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
    assert list(service().permissions) == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(service().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_what_each_role_gets():
    everything = set(PERMISSIONS)
    assert grants_by_role(service()) == {
        "hub_owner": everything,
        "hub_admin": everything,
        "hub_manager": everything - ADMIN_ONLY,
        "hub_employee": EMPLOYEE,
        "hub_accountant": set(),
    }


def test_navigation_is_the_three_tabs_of_the_old_module_and_the_settings_with_registered_icons():
    entries = service().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.icon, entry.path, entry.permission) for entry in entries] == [
        ("services", "Services", "ion:briefcase-outline", "/service/services", "service.view_service"),
        ("categories", "Categories", "ion:pricetags-outline", "/service/categories", "service.view_category"),
        ("packages", "Packages", "ion:gift-outline", "/service/packages", "service.view_package"),
        ("settings", "Settings", "ion:settings-outline", "/service/settings", "service.manage_settings"),
    ]


#: What only names a record on the assistant's card, and what only the recovery from a separate copy runs (a service
#: made again with who performed it, what the business kept put back into a category brought back, which service
#: stands for one of the copy's): no tool (``INTERNAL``).
NO_TOOL = {
    "service.record.get",
    "service.service.recover",
    "service.category.recover",
    "service.service.return_to_category",
    "service.category.return_to_parent",
    "service.service.standing_for",
}


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none. A tool says what a
    # person types to ask for it, in both languages (live.E020: Services is listed in
    # LIVE_ASSISTANT_ASKS_REQUIRED).
    from live.operations import AI, INTERNAL, MIN_ASKS, registry

    operations = [op for name, op in registry.items() if name.startswith("service.")]
    # 45 + the service's image (SERVICE-F34, F35): set_image, upload_image, suggest_image
    # + what the assistant's card names by its id: assignment.get, grant.get, session.get
    # + what it names of Sales and Appointments: record.get, which is no tool
    # + a service made again from a separate copy with who performed it: service.recover, no tool either,
    # + and a category made again from it: category.recover, no tool either,
    # + and what the business kept put back into it: service.return_to_category, category.return_to_parent, neither,
    # + and which service stands for one of the copy's, which Price Lists asks: service.standing_for, no tool either,
    # + and saying later which sale charged a voucher granted without it: grant.link.
    assert len(operations) == 58
    for op in operations:
        if op.name in NO_TOOL:
            assert op.ai is INTERNAL, op.name
            continue
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        if isinstance(op.ai_spec(), AI):
            expected |= {"asks"}
            said = {language: len(op.ai.get("asks", {}).get(language, ())) for language in ("en", "es")}
            assert min(said.values()) >= MIN_ASKS, (op.name, said)
        # The card of a voucher puts first the voucher, whose it is and its sale (hub#2347); the one of several services,
        # each by its name (hub#2619).
        if op.name in {"service.grant.create", "service.service.bulk_create"}:
            expected |= {"summary"}
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


# The Home's step «Your service catalogue», which reads the catalog's status. The old module declared no panel and no
# bell row.


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
    assert home.setup_steps.level_of(f"service.{step.key}", step.required) == home.setup_steps.LEVEL_FUNCTIONAL


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
    icons = shell_icon_registry()
    assert f"'{step.icon.removeprefix('ion:')}'" in icons


def test_services_brings_no_panels_and_no_bell_rows_to_the_home():
    # The old module declared neither (its module.json has `widgets` and `bell` null).
    assert (service().widgets, service().bell) == ([], [])


def test_its_help_window_plays_the_app_s_tour_in_spanish_and_in_english():
    assert service().help.videos == {"es": "toNEQIwtQDY", "en": "vxEm9WTDpi0"}


#: The short video of each task, with the flows it shows: its Spanish and its English one.
TASK_VIDEOS = [
    (("SERVICE-F01", "SERVICE-F02", "SERVICE-F04"), "LbOhuQ82bpw", "RncbXpYLq-I"),
    (("SERVICE-F03",), "Vr7GaLsXYy0", "Ul5ANHNCxTo"),
    (("SERVICE-F31", "SERVICE-F32"), "zX1YGJDGZgs", "P2zoniTyTbU"),
    (("SERVICE-F07", "SERVICE-F08"), "lSNrQpprRDU", "VXDOqc0EWU8"),
    (("SERVICE-F12", "SERVICE-F13"), "oD_kZLu2xYQ", "3XPQhS5SNrc"),
]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_task_of_the_help_window_shows_its_short_videos_in_the_person_s_language(language):
    assert help_videos.shown("service", language) == help_videos.by_task(TASK_VIDEOS, language)
