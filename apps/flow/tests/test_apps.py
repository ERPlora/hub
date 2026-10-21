"""The flow app declares its module metadata, its menu entry, its permissions, what each role gets, its
scheduled tasks and the assistant's contract of every operation (``ai`` and described input fields)."""

import pytest
from django.apps import apps
from django.utils import translation
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

PERMISSIONS = ["flow.view", "flow.manage", "flow.answer", "flow.answer_manager"]
QUERIES = {
    "flow.flow.list",
    "flow.flow.detail",
    "flow.flow.status",
    "flow.flow.test",
    "flow.run.list",
    "flow.draft.list",
    "flow.catalog.read",
    "flow.event.sample",
    "flow.secret.list",
    "flow.question.list",
}
COMMANDS = {
    "flow.flow.create",
    "flow.flow.update",
    "flow.flow.set_enabled",
    "flow.flow.duplicate",
    "flow.flow.delete",
    "flow.flow.grant",
    "flow.flow.run",
    "flow.draft.propose",
    "flow.draft.dismiss",
    "flow.run.react",
    "flow.schedule.fire_due",
    "flow.run.resume_due",
    "flow.run.prune",
    "flow.run.retry",
    "flow.secret.set",
    "flow.secret.delete",
    "flow.run.call",
    "flow.run.claim_call",
    "flow.run.record_call",
    "flow.question.answer",
    "flow.question.expire_due",
}
# What the assistant confirms before running: turning on or off, granting, running by hand or resuming
# a failed run, deleting, a secret, and answering a question a person was asked (FLOW-F29).
HIGH_RISK = {
    "flow.flow.set_enabled",
    "flow.flow.grant",
    "flow.flow.run",
    "flow.run.retry",
    "flow.flow.delete",
    "flow.secret.set",
    "flow.secret.delete",
    "flow.question.answer",
}
# Run only by the platform: the reactions (to every event, and to a run parked on a call) and the
# scheduled tasks.
SYSTEM = {
    "flow.run.react",
    "flow.run.call",
    "flow.schedule.fire_due",
    "flow.run.resume_due",
    "flow.run.prune",
    "flow.run.claim_call",
    "flow.run.record_call",
    "flow.question.expire_due",
}


def flow_app():
    return apps.get_app_config("flow")


@pytest.fixture
def flow_operations():
    from apps.flow import queries, services  # noqa: F401  (importing them registers the operations)

    return {name: op for name, op in registry.items() if op.app_label == "flow"}


def test_flow_is_a_live_app_that_requires_no_other_app():
    config = flow_app()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.flow"
    assert config.label == "flow"
    # Actions and reads of other apps are called by their name, never by their models (WORKBOOK).
    assert config.requires == []


def test_flow_is_a_free_module_of_the_organization_group():
    config = flow_app()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    # Registered in the shell (ION_ICONS); the old `git-branch` waits in UI-REQUESTS.md.
    assert config.icon == "ion:sync-outline"
    assert str(config.verbose_name) == "Automations"


def test_flow_has_the_store_metadata_and_belongs_to_both_verticals():
    config = flow_app()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert flow_app().permissions == PERMISSIONS


def test_only_the_owner_and_the_admin_get_it_the_others_only_answer_what_they_are_asked():
    config = flow_app()
    assert set(config.role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    # FLOW-F29: a manager answers what is asked of managers and of employees; an employee, of employees.
    assert permissions_for_role([config], "hub_manager") == {"flow.answer", "flow.answer_manager"}
    assert permissions_for_role([config], "hub_employee") == {"flow.answer"}


def test_navigation_is_the_one_entry_of_the_old_module():
    entries = flow_app().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.icon, entry.path) for entry in entries
    ] == [
        ("automations", "Automations", "ion:sync-outline", "/flow/automations"),
    ]


def test_the_scheduled_tasks_run_as_the_platform_two_every_minute_and_the_prune_every_hour():
    assert flow_app().scheduled_tasks == [
        {
            "name": "fire_due",
            "operation": "flow.schedule.fire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
        {
            "name": "resume_due",
            "operation": "flow.run.resume_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
        {
            "name": "prune",
            "operation": "flow.run.prune",
            "cron": "17 * * * *",
            "catch_up": "collapse",
        },
        # FLOW-F30: the questions nobody answered in time.
        {
            "name": "expire_questions",
            "operation": "flow.question.expire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app(flow_operations):
    assert {
        name for name, op in flow_operations.items() if op.kind == "query"
    } == QUERIES
    assert {
        name for name, op in flow_operations.items() if op.kind == "command"
    } == COMMANDS


def test_every_operation_tells_the_assistant_what_it_does(flow_operations):
    for name, op in flow_operations.items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_the_high_risk_commands(flow_operations):
    assert {
        name for name, op in flow_operations.items() if op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant(flow_operations):
    missing = [
        f"{op.name}: {field_name}"
        for op in flow_operations.values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []


def test_the_engine_is_run_only_by_the_platform(flow_operations):
    # No role holds the system permission: no person and no API key reaches the engine.
    for name in SYSTEM:
        assert flow_operations[name].permission == "flow.system", name
    assert "flow.system" not in flow_app().permissions


def test_people_need_view_to_read_and_manage_to_change(flow_operations):
    for name, op in flow_operations.items():
        if name in SYSTEM:
            continue
        if name in {"flow.question.list", "flow.question.answer"}:
            # FLOW-F29: whoever may answer something; each question then asks for its own role.
            assert op.permission == "flow.answer", name
        elif name in {"flow.flow.test", "flow.event.sample", "flow.secret.list"}:
            # They read the outbox's payloads as they came, or the secrets' names: only who manages.
            assert op.permission == "flow.manage", name
        elif op.kind == "query":
            assert op.permission == "flow.view", name
        else:
            assert op.permission == "flow.manage", name


def test_the_store_card_promises_only_what_phase_1_does():
    # FLOW-F21 and FLOW-F17 are partial: nothing starts an automation on an event of another app, and
    # the Hub has no assistant. The store's card says what it does today and what comes later, like the
    # guide and the WORKBOOK.
    config = flow_app()
    expected = {
        "en": ("when something happens", "assistant", "when a sale is charged", "comes in a later version"),
        "es": ("cuando pasa algo", "asistente", "cuando se cobra una venta", "llega en una versión posterior"),
    }
    for language, (happens, assistant, sale, later) in expected.items():
        with translation.override(language):
            summary, description = str(config.summary).lower(), str(config.description).lower()
        assert happens not in summary, summary
        assert assistant not in summary and assistant not in description
        assert sale not in description, description
        assert later in description, description
