"""The verifactu app declares its module metadata, its menu, its permissions, what each role gets, its scheduled
task and, for the assistant, every operation and every input field."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role

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
    "verifactu.representation.submit",
    "verifactu.representation.model",
}
#: High risk: sending to the AEAT, the queue, correcting and cancelling, the chain's recovery and the configuration.
HIGH = {
    "verifactu.record.correct",
    "verifactu.record.cancel",
    "verifactu.record.transmit",
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
