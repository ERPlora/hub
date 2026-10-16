"""The modifier app declares its module metadata, its menu entry, its permissions and what each role gets."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role


def modifier():
    return apps.get_app_config("modifier")


def test_modifier_is_an_installed_live_app():
    config = modifier()
    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label) == ("apps.modifier", "modifier")
    assert "apps.modifier" in settings.INSTALLED_APPS
    # A link points at a product or a category of Inventory; an option at a tax category of Taxes.
    assert config.requires == ["inventory", "tax"]


def test_modifier_is_a_free_module_of_the_catalog_group():
    config = modifier()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    # The old `options-outline` is a pair of sliders: Lucide's, registered in the shell, is the same
    # drawing (Combo already took `ion:layers-outline`).
    assert config.icon == "lucide:sliders-horizontal"
    assert str(config.verbose_name) == "Modifiers"


def test_modifier_is_in_the_store_and_in_the_restaurant_vertical():
    config = modifier()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions():
    # `modifier.system` (the reactions to Inventory) is declared by no role on purpose.
    assert modifier().permissions == ["modifier.view", "modifier.manage"]


def test_roles():
    config = modifier()
    assert set(config.role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == {
            "modifier.view",
            "modifier.manage",
        }
    # The cashier reads the groups of a product and has the picks valued; it never edits the catalog.
    assert permissions_for_role([config], "hub_employee") == {"modifier.view"}


def test_navigation_is_one_entry_like_the_old_module():
    entries = modifier().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(e.id, str(e.label), e.path, e.icon) for e in entries] == [
        ("groups", "Modifiers", "/modifier/groups", "lucide:sliders-horizontal"),
    ]


def test_the_workbook_has_the_user_part_and_the_maintainers_part():
    workbook = (Path(modifier().path) / "WORKBOOK.md").read_text()
    assert "\n## Para quien lo mantiene\n" in workbook
    assert workbook.index("## Flujos") < workbook.index("## Para quien lo mantiene")
    for section in ("### Contrato con Ventas", "### Contrato con Cocina"):
        assert section in workbook


def test_every_operation_is_described_for_the_assistant():
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("modifier.")}
    assert sorted(ops) == sorted(
        [
            "modifier.group.list",
            "modifier.group.get",
            "modifier.group.for_target",
            "modifier.option.list",
            "modifier.link.list",
            "modifier.selection.resolve",
            "modifier.group.create",
            "modifier.group.update",
            "modifier.group.delete",
            "modifier.option.create",
            "modifier.option.update",
            "modifier.option.delete",
            "modifier.link.attach",
            "modifier.link.detach",
            "modifier.link.drop_product",
            "modifier.link.drop_category",
        ]
    )
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name
    high = {
        name
        for name, op in ops.items()
        if op.kind == "command" and op.ai["risk"] == "high"
    }
    assert high == {"modifier.group.delete", "modifier.option.delete"}


def test_every_input_field_says_what_it_is():
    # The input schemas are the JSON Schema of the assistant's tools: a field without a description
    # is a field the assistant guesses.
    from live.operations import registry

    for name, op in registry.items():
        if not name.startswith("modifier."):
            continue
        for field, info in op.input.model_fields.items():
            assert info.description, f"{name}.{field}"


def test_the_pos_reads_are_open_to_api_keys():
    from live.operations import registry

    exposed = {
        name
        for name, op in registry.items()
        if name.startswith("modifier.") and op.expose_api
    }
    assert {
        "modifier.group.for_target",
        "modifier.selection.resolve",
        "modifier.group.list",
    } <= exposed
    # The reactions to Inventory are the platform's only.
    assert not exposed & {"modifier.link.drop_product", "modifier.link.drop_category"}
