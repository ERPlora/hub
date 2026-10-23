"""The verifactu app declares its module metadata, its menu, its permissions, what each role gets, its scheduled
task, its hooks of the Home and, for the assistant, every operation and every input field."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    Category,
    LiveAppConfig,
    Nav,
    SetupCheck,
    SetupStep,
    Widget,
    module_configs,
    permissions_for_role,
)

from apps.verifactu import events as E
from base import home

PERMISSIONS = [
    "verifactu.view_record",
    "verifactu.add_record",
    "verifactu.transmit_record",
    "verifactu.correct_record",
    "verifactu.configure",
]


def verifactu():
    return apps.get_app_config("verifactu")


def test_verifactu_is_an_installed_live_app():
    config = verifactu()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.verifactu"
    assert config.label == "verifactu"
    assert "apps.verifactu" in settings.INSTALLED_APPS


def test_it_requires_invoicing_alone():
    # A record is born from an issued invoice, read from its row by a foreign key.
    assert verifactu().requires == ["invoice"]


def test_verifactu_is_a_free_module_of_the_sales_group_in_both_verticals():
    config = verifactu()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    # Registered in the shell (packages/ui/src/shell/icons.ts); the old shield-checkmark-outline waits in
    # apps/verifactu/UI-REQUESTS.md.
    assert config.icon == "lucide:shield-check"
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert verifactu().permissions == PERMISSIONS


def test_roles():
    config = verifactu()
    assert set(config.role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    # The manager watches and pushes the queue; correcting, cancelling and configuring are the owner's.
    assert permissions_for_role([config], "hub_manager") == {
        "verifactu.view_record",
        "verifactu.add_record",
        "verifactu.transmit_record",
    }
    # The employee looks; recording an issued invoice is what Invoicing asks with the issuer's session.
    assert permissions_for_role([config], "hub_employee") == {
        "verifactu.view_record",
        "verifactu.add_record",
    }


def test_navigation_is_the_six_tabs_of_the_old_module_with_registered_icons():
    entries = verifactu().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("records", "Records", "/verifactu/records", "ion:list-outline"),
        ("contingency", "Contingency", "/verifactu/contingency", "ion:warning-outline"),
        ("events", "Events", "/verifactu/events", "ion:time-outline"),
        ("recovery", "Recovery", "/verifactu/recovery", "lucide:shield-check"),
        ("config", "Configuration", "/verifactu/config", "ion:key-outline"),
        ("settings", "Settings", "/verifactu/settings", "ion:settings-outline"),
    ]


def test_the_queue_is_sent_every_minute_by_the_worker():
    # Declared in the AppConfig for the phase-2 worker, which runs it as the system; collapsed on catch-up.
    assert verifactu().scheduled_tasks == [
        {
            "name": "process_queue",
            "operation": "verifactu.contingency.process",
            "cron": "* * * * *",
            "catch_up": "collapse",
        }
    ]


OPERATIONS = {
    "verifactu.config.get",
    "verifactu.record.list",
    "verifactu.record.get",
    "verifactu.record.by_invoice",
    "verifactu.contingency.list",
    "verifactu.event.list",
    "verifactu.stats.compliance_summary",
    "verifactu.stats.records_by_status",
    "verifactu.stats.contingency_summary",
    "verifactu.stats.events_recent",
    "verifactu.aeat_record.list",
    "verifactu.chain.status",
    "verifactu.diagnostic.last",
    "verifactu.record.create",
    "verifactu.record.correct",
    "verifactu.record.cancel",
    "verifactu.record.transmit",
    "verifactu.record.reconcile",
    "verifactu.contingency.process",
    "verifactu.contingency.retry",
    "verifactu.chain.validate",
    "verifactu.aeat.query",
    "verifactu.chain.recover_from_aeat",
    "verifactu.chain.recover_manual",
    "verifactu.diagnostic.run",
    "verifactu.test_invoice.create",
    "verifactu.config.update",
    "verifactu.config.go_live",
    "verifactu.config.back_to_testing",
    "verifactu.certificate.upload",
    "verifactu.certificate.remove",
    "verifactu.config.sync",
    "verifactu.config.follow_deployment",
    "verifactu.representation.submit",
    "verifactu.representation.model",
}
#: High risk: sending to the AEAT, the queue, correcting and cancelling, the chain's recovery and the configuration.
HIGH = {
    "verifactu.record.correct",
    "verifactu.record.cancel",
    "verifactu.record.transmit",
    "verifactu.record.reconcile",
    "verifactu.contingency.process",
    "verifactu.contingency.retry",
    "verifactu.aeat.query",
    "verifactu.chain.recover_from_aeat",
    "verifactu.chain.recover_manual",
    "verifactu.test_invoice.create",
    "verifactu.config.update",
    "verifactu.config.go_live",
    "verifactu.config.back_to_testing",
    "verifactu.certificate.upload",
    "verifactu.certificate.remove",
    "verifactu.config.sync",
    "verifactu.config.follow_deployment",
    "verifactu.representation.submit",
}


def test_every_operation_is_described_for_the_assistant():
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("verifactu.")}
    assert set(ops) == OPERATIONS
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") == ("high" if name in HIGH else "normal"), name
        else:
            assert "risk" not in op.ai, name


def test_every_input_field_says_what_it_is():
    from live.operations import registry

    for name, op in registry.items():
        if name.startswith("verifactu."):
            for field_name, field in op.input.model_fields.items():
                assert (field.description or "").strip(), f"{name}.{field_name}"


def test_the_system_alone_receives_the_accounts_photo():
    from live.operations import registry

    assert registry["verifactu.config.sync"].permission == "verifactu.sync_config"
    assert "verifactu.sync_config" not in verifactu().permissions


# The Home's hooks (PLAN-HUB round 2026-10-21; FIX-VERIFACTU-SETUP-HOOKS): the old module's module.json `setup` and
# `widgets` (it had no `bell`), ported to the ways a business reaches the AEAT now (PLAN §30, VeriFactu on Free).


def test_the_homes_step_is_the_old_set_up_verifactu_on_the_way_to_production():
    """«Set up VeriFactu»: done once the chosen way could carry the records to the AEAT of production (ERPlora's with
    the signed authorisation approved, or the business's own valid certificate), read from the configuration's own
    query; whoever configures VeriFactu sets it up in Configuration."""
    (step,) = verifactu().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        list(step.configured_when),
        dict(step.params),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
    ) == (
        "sending_route",
        "verifactu.config.get",
        [SetupCheck(field="route_ready_for_production", truthy=True)],
        {},
        "/verifactu/config",
        "verifactu.configure",
        "lucide:shield-check",
        [],
        None,
    )
    assert "route_ready_for_production" in registry_output("verifactu.config.get")


def registry_output(name: str) -> set[str]:
    from live.operations import registry

    return set(registry[name].output.model_fields)


def test_the_step_is_important_but_never_says_it_stops_the_sale():
    """gh:hub#1726: the old checklist painted VeriFactu as «Necesario para vender» while the till sold without it.
    Testing files without the step, so it is functional («Important»), never base's legal level («Needed to
    invoice»), and its text names what it is for, not a wall."""
    (step,) = verifactu().setup
    assert step.required is True
    assert home.level_of(f"verifactu.{step.key}", step.required) == home.LEVEL_FUNCTIONAL
    for language in ("en", "es"):
        with translation.override(language):
            text = f"{step.title} {step.description}".lower()
        for wall in ("sell", "vender", "invoice", "facturar"):
            assert f"to {wall}" not in text and f"para {wall}" not in text, (language, wall)


def test_the_step_speaks_the_language_of_whoever_reads_it():
    """gh:verifactu#143: with the app in English the old Home said «Configura VeriFactu»; the Spanish reader keeps
    the title they already knew, and the description says the ways of today."""
    (step,) = verifactu().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == (
        "Set up VeriFactu",
        "Sign the authorisation for ERPlora to send your invoices to the AEAT, or upload your business "
        "certificate.",
    )
    assert spanish == (
        "Configura VeriFactu",
        "Firma la autorización para que ERPlora envíe tus facturas a la AEAT, o sube el certificado del negocio.",
    )


def test_the_step_is_refreshed_when_the_configuration_changes():
    # A route chosen, a certificate uploaded or removed and the account's photo all say verifactu.config.changed.
    (step,) = verifactu().setup
    assert list(step.refresh_on) == [E.CONFIG_CHANGED]
    assert E.CONFIG_CHANGED in live_registry.subscribable[step.operation]


PANELS = ["pending", "contingency", "by_status", "events"]


def test_the_homes_panels_are_the_old_modules_four():
    """What is not in the AEAT yet on by default, the contingency queue, the records by status and the latest AEAT
    events to turn on, each on the query of the old one; the events in a component of the app, which names each
    event's type in the reader's language (gh:verifactu#139: never its code)."""
    panels = verifactu().widgets
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
        (
            "pending",
            "kpi",
            None,
            "verifactu.stats.compliance_summary",
            "sm",
            True,
            "verifactu.view_record",
            {},
            {"value": "pending_count"},
            {"format": "number"},
        ),
        (
            "contingency",
            "stat",
            None,
            "verifactu.stats.contingency_summary",
            "sm",
            False,
            "verifactu.view_record",
            {},
            {"value": "queued_count", "severity": "severity"},
            {"format": "number"},
        ),
        (
            "by_status",
            "bar-list",
            None,
            "verifactu.stats.records_by_status",
            "md",
            False,
            "verifactu.view_record",
            {},
            {"label": "label", "value": "total"},
            {"valueFormat": "number"},
        ),
        (
            "events",
            None,
            "RecentEventsPanel",
            None,
            "md",
            False,
            "verifactu.view_record",
            {},
            {},
            {},
        ),
    ]
    # Every business: the old panels named every sector. Grouped under the app's own name in «Customize panel».
    assert all(not panel.verticals and not panel.category for panel in panels)
    component = Path(verifactu().path) / "frontend" / "components" / "RecentEventsPanel.vue"
    assert component.is_file()


def test_the_panels_are_titled_in_english_and_in_spanish_as_the_old_ones():
    with translation.override("en"):
        english = [str(panel.title) for panel in verifactu().widgets]
    with translation.override("es"):
        spanish = [str(panel.title) for panel in verifactu().widgets]
    assert english == [
        "VeriFactu pending",
        "Contingency queue",
        "Records by status",
        "Recent AEAT events",
    ]
    assert spanish == [
        "Pendientes VeriFactu",
        "Cola de contingencia",
        "Registros por estado",
        "Eventos AEAT recientes",
    ]


def test_each_panel_is_refreshed_by_the_events_that_re_run_its_query():
    panels = {panel.key: panel for panel in verifactu().widgets}
    assert list(panels) == PANELS
    assert {key: list(panel.refresh_on) for key, panel in panels.items()} == {
        "pending": E.RECORD_EVENTS,
        "contingency": E.RECORD_EVENTS,
        "by_status": E.RECORD_EVENTS,
        "events": E.ALL,
    }
    for key, panel in panels.items():
        operation = panel.operation or "verifactu.stats.events_recent"
        assert live_registry.is_subscribable(operation), key
        assert set(panel.refresh_on) == set(live_registry.subscribable[operation]), key


def test_the_hooks_icons_are_registered_in_the_shell():
    # Registered icons only (an unregistered one paints nothing): the old `shield-checkmark-outline` and
    # `stats-chart-outline` wait in UI-REQUESTS.md.
    (step,) = verifactu().setup
    icons = [step.icon, *(panel.icon for panel in verifactu().widgets)]
    assert icons == [
        "lucide:shield-check",
        "lucide:shield-check",
        "ion:warning-outline",
        "ion:list-outline",
        "ion:time-outline",
    ]
    shell = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in icons:
        name = icon.removeprefix("ion:")
        assert f"'{name}'" in shell, icon


def test_verifactu_has_no_bell_counters():
    # The old module declared none (its module.json has no `bell`).
    assert verifactu().bell == []
