"""The task app declares its module metadata, its menu entries, its permissions, what each role gets,
and the assistant's contract of every operation (``ai`` and described input fields)."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import registry

from apps.task import queries, services  # noqa: F401  (importing them registers the operations)

PERMISSIONS = [
    "task.view",
    "task.view_all",
    "task.add",
    "task.change",
    "task.change_all",
    "task.delete",
    "task.manage_project",
]
QUERIES = {
    "task.task.list",
    "task.task.mine",
    "task.task.detail",
    "task.task.subtasks",
    "task.comment.list",
    "task.project.list",
    "task.project.detail",
}
COMMANDS = {
    "task.task.create",
    "task.task.update",
    "task.task.set_status",
    "task.task.complete",
    "task.task.assign",
    "task.task.delete",
    "task.task.release_member",
    "task.comment.add",
    "task.project.create",
    "task.project.update",
    "task.project.delete",
}
# What the assistant confirms before running: a deletion.
HIGH_RISK = {"task.task.delete", "task.project.delete"}


def task_app():
    return apps.get_app_config("task")


def task_operations():
    return {name: op for name, op in registry.items() if op.app_label == "task"}


def test_task_is_a_live_app_that_requires_staff():
    config = task_app()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.task"
    assert config.label == "task"
    # The assignee and a project's owner are staff records (WORKBOOK «Referencia adoptada»).
    assert config.requires == ["staff"]


def test_task_is_a_free_module_of_the_organization_group():
    config = task_app()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    assert config.icon == "ion:checkmark-circle-outline"
    assert str(config.verbose_name) == "Tasks"


def test_task_has_the_store_metadata_and_belongs_to_both_verticals():
    config = task_app()
    assert 0 < len(str(config.summary)) <= 120
    assert "\n" not in str(config.summary)
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert task_app().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(task_app().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_the_manager_gets_everything_and_the_employee_their_own_tasks():
    config = task_app()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == {
        "task.view",
        "task.add",
        "task.change",
    }


def test_every_granted_permission_is_declared():
    config = task_app()
    for granted in config.role_permissions.values():
        for permission in granted:
            assert permission == "task.*" or permission in config.permissions, permission


def test_navigation_is_the_two_tabs_of_the_old_module_with_registered_icons():
    entries = task_app().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.icon, entry.path) for entry in entries] == [
        ("tasks", "Tasks", "ion:checkmark-circle-outline", "/task/tasks"),
        ("projects", "Projects", "ion:file-tray-outline", "/task/projects"),
    ]


# The operations and the assistant's contract


def test_the_operations_of_the_app():
    operations = task_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == QUERIES
    assert {name for name, op in operations.items() if op.kind == "command"} == COMMANDS


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in task_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_the_high_risk_commands():
    assert {
        name for name, op in task_operations().items() if op.ai.get("risk") == "high"
    } == HIGH_RISK


def test_every_input_field_is_described_for_the_assistant():
    missing = [
        f"{op.name}: {field_name}"
        for op in task_operations().values()
        for field_name, field in op.input.model_fields.items()
        if not (field.description or "").strip()
    ]
    assert missing == []


def test_the_reaction_is_run_only_by_the_platform():
    # No role holds the system permission: no person and no API key reaches the reaction.
    op = registry["task.task.release_member"]
    assert op.permission == "task.system"
    assert "task.system" not in task_app().permissions
