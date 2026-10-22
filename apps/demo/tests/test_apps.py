"""The demo app declares its module metadata, its menu entry, its permissions and what each role gets."""

from django.apps import apps
from django.utils import translation
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, module_configs, permissions_for_role

from apps.demo import events


def demo():
    return apps.get_app_config("demo")


def test_demo_is_a_live_app():
    config = demo()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.demo"
    assert config.requires == []


def test_demo_is_a_free_module_of_the_organization_group():
    config = demo()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    # The same icon as its menu entry, with its Iconify set prefix.
    assert config.icon == "ion:flask-outline"


def test_demo_has_the_store_metadata_but_stays_out_of_the_store():
    # Round 16 (PLAN §21): every module declares what the public store shows; demo is the technical
    # reference and is not sold (its WORKBOOK), so listed = False and it belongs to no vertical.
    config = demo()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == []
    assert config.listed is False


def test_permissions():
    assert demo().permissions == ["demo.view", "demo.manage"]


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(demo().role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}


def test_roles():
    config = demo()
    assert permissions_for_role([config], "hub_owner") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_admin") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_manager") == {"demo.view", "demo.manage"}
    assert permissions_for_role([config], "hub_employee") == {"demo.view"}


def test_navigation_points_at_the_item_list_with_an_iconify_icon():
    [entry] = demo().navigation
    assert isinstance(entry, Nav)
    assert (entry.id, str(entry.label), entry.path) == ("demo", "Demo", "/demo/items")
    # Iconify names carry their set prefix (HubIcon, working-rules §11).
    assert entry.icon == "ion:flask-outline"


# The assistant's contract: every operation is one of its tools (CLAUDE.md «Un solo camino hacia el servidor»).


def demo_operations():
    from live.operations import registry

    return {name: op for name, op in registry.items() if name.startswith("demo.")}


def test_the_operations_of_the_app():
    operations = demo_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == {
        "demo.item.list",
        "demo.item.detail",
        "demo.item.stats",
        "demo.item.open_count",
    }
    assert {name for name, op in operations.items() if op.kind == "command"} == {
        "demo.item.create",
        "demo.item.update",
        "demo.item.delete",
        "demo.item.add_line",
    }


def test_every_operation_tells_the_assistant_what_it_does():
    for name, op in demo_operations().items():
        assert isinstance(op.ai, dict), name
        assert str(op.ai.get("description", "")).strip(), name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_deleting_an_item_is_the_only_high_risk_command():
    # It takes the item's lines with it and cannot be undone; the rest are undone with another command.
    assert {name for name, op in demo_operations().items() if op.ai and op.ai.get("risk") == "high"} == {
        "demo.item.delete"
    }


def test_the_homes_hooks_are_the_example_every_app_copies():
    """PLAN-HUB round 2026-10-21: one step, one panel and one counter, each on a query of its own queries.py. The
    demo is out of the store, so base shows them only where SHOW_UNLISTED_MODULES is on (development, tests, e2e)."""
    config = apps.get_app_config("demo")
    [step] = config.setup
    [panel] = config.widgets
    [counter] = config.bell

    assert (step.key, step.operation, step.permission, step.required, step.route, step.icon) == (
        "first_item",
        "demo.item.stats",
        "demo.manage",
        False,
        "/demo/items/new",
        "ion:flask-outline",
    )
    assert list(step.configured_when) == [SetupCheck(field="total", truthy=True)]
    with translation.override("en"):
        texts = (str(step.title), str(step.description), str(counter.label))
    assert texts == (
        "Create your first item",
        "Add an item and watch it appear on every screen of the business at once.",
        "Open demo items",
    )
    assert (panel.key, panel.kind, panel.operation, dict(panel.map), panel.default, panel.permission, panel.size) == (
        "open_items",
        "kpi",
        "demo.item.stats",
        {"value": "open"},
        True,
        "demo.manage",
        "sm",
    )
    assert (counter.key, counter.operation, counter.route, counter.permission) == (
        "open_items",
        "demo.item.open_count",
        "/demo/items",
        "demo.view",
    )
    for hook in (step, panel, counter):
        assert set(hook.refresh_on) <= set(events.ALL), hook.key
    assert config.listed is False
