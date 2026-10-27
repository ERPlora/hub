"""The printing app declares its module metadata, its menu, its permissions, what each role gets and its hooks of the
Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import BellCounter, Category, LiveAppConfig, SetupCheck, SetupStep, module_configs, permissions_for_role
from live.operations import registry

from apps.printing import events as E
from base import home

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
        ("devices", "Devices", "lucide:smartphone", "/printing/devices"),
        ("jobs", "Queue", "ion:list-outline", "/printing/jobs"),
        ("settings", "Settings", "ion:settings-outline", "/printing/settings"),
    ]


def test_the_queue_forgets_its_finished_jobs_once_an_hour():
    # PRINTING-F20: run by the worker as the platform (cron in UTC), never by a person.
    assert config().scheduled_tasks == [
        {"name": "prune", "operation": "printing.job.prune", "cron": "23 * * * *", "catch_up": "collapse"}
    ]


# The Home's hooks (PLAN-HUB round 2026-10-21; FIX-PRINTING-SETUP-HOOKS): the old hub's core item «Set up your printer»
# (setup_status.rs ITEM_PRINTER, hub#1948) and its bell row «Nothing is printing “…”» (old-hub:HUB_SHELL-F63,
# hub#987), which live in Printing here. The old module itself declared neither, nor any panel.

#: What changes whether a device set up here reaches an active receipt printer: a device set up, changed or retired,
#: and a printer switched off, on, or to another function or connection. Never a printer just added (no device
#: reaches it yet).
COVERAGE = [E.PRINTER_UPDATED, *E.DEVICE_EVENTS]
#: What changes how many jobs wait that no device set up here can print: a job queued (a new one, a retry, one back
#: from a device that did not answer or that failed it, one moved off a printer), cancelled, and what decides who
#: reaches its printer.
UNATTENDED = [E.JOB_QUEUED, E.JOB_FAILED, E.JOB_CANCELLED, E.PRINTER_UPDATED, *E.DEVICE_EVENTS]


def test_the_homes_step_is_set_up_your_printer_done_once_a_device_prints_the_receipts():
    """The old core item, same order and words: recommended (without a printer the business still sells, hub#1731),
    done once a device set up here reaches an active receipt printer (the old «registered for the receipt station»,
    live or not), for whoever sets printers and devices up, leading to the devices."""
    (step,) = config().setup
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
        "printer",
        "printing.device.coverage",
        {"usage": "receipt"},
        [SetupCheck(field="configured", truthy=True)],
        "/printing/devices",
        "printing.manage_settings",
        "lucide:receipt",
        [],
        70,
        False,
    )
    assert "configured" in registry[step.operation].output.model_fields
    assert home.level_of(f"printing.{step.key}", step.required) == home.LEVEL_RECOMMENDED


def test_the_step_says_the_old_words_in_the_language_of_whoever_reads_it():
    (step,) = config().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == (
        "Set up your printer",
        "Register the device that prints your customers' receipts, so the first sale comes out on paper.",
    )
    assert spanish == (
        "Configura la impresora",
        "Da de alta el dispositivo que imprime los tiques de tus clientes, para que la primera venta salga en papel.",
    )


def test_the_step_is_refreshed_on_what_changes_who_prints_the_receipts():
    (step,) = config().setup
    assert list(step.refresh_on) == COVERAGE
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


FUNCTIONS = [("receipt", "Receipt", "Recibo"), ("kitchen", "Kitchen", "Cocina"), ("bar", "Bar", "Barra"), ("label", "Label", "Etiqueta")]


def test_the_bell_says_which_function_nobody_is_printing_one_row_each():
    """One row per function, as the old bell (the kitchen and the bar are two places to go), named as Printing names
    them (the old row showed its internal key, HUB_SHELL-F63), to everybody with Printing (who stands at the counter can
    switch the till on), leading to the printers' state by function (gh:hub#2016)."""
    counters = config().bell
    assert all(isinstance(counter, BellCounter) for counter in counters)
    assert [
        (counter.key, counter.operation, dict(counter.params), counter.route, str(counter.label), counter.icon, counter.permission)
        for counter in counters
    ] == [
        (
            f"stalled_{usage}",
            "printing.device.coverage",
            {"usage": usage},
            "/printing/printers",
            f"Nothing is printing “{english}”",
            "lucide:receipt",
            "printing.view_settings",
        )
        for usage, english, _spanish in FUNCTIONS
    ]
    assert all(list(counter.refresh_on) == UNATTENDED for counter in counters)


def test_the_bell_rows_say_the_old_words_in_spanish():
    with translation.override("es"):
        labels = [str(counter.label) for counter in config().bell]
    assert labels == [f"Nadie está imprimiendo «{spanish}»" for _usage, _english, spanish in FUNCTIONS]


def test_the_hooks_query_is_re_run_on_their_events_and_their_icon_is_registered():
    (step,) = config().setup
    assert live_registry.is_subscribable("printing.device.coverage")
    assert set(UNATTENDED) <= set(live_registry.subscribable["printing.device.coverage"])
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert all(f"'{icon.removeprefix('ion:')}'" in icons for icon in {step.icon, *(counter.icon for counter in config().bell)})


def test_printing_brings_no_panels_to_the_home():
    # The old module declared none (its module.json has no `widgets`), nor did the old core for printing.
    assert config().widgets == []
