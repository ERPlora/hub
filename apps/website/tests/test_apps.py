"""The website app declares its module metadata, its menu entry, its permissions and what each role gets."""

from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role


def website():
    return apps.get_app_config("website")


def test_website_is_a_module_with_no_requires_and_its_nav():
    config = website()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.website"
    assert config.kind == "app"
    assert config in module_configs()
    # The catalog of another app is read by its operation's name, never by its models (as apps.flow).
    assert config.requires == []
    [entry] = config.navigation
    assert isinstance(entry, Nav)
    assert (entry.id, str(entry.label), entry.icon, entry.path) == ("site", "Website", "ion:globe-outline", "/website")


def test_website_is_a_free_module_of_the_organization_group_sold_to_both_verticals():
    config = website()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    assert config.icon == "ion:globe-outline"
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)


def test_permissions_and_roles():
    config = website()
    assert config.permissions == ["website.view", "website.manage"]
    assert set(config.role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}
    assert permissions_for_role([config], "hub_owner") == {"website.view", "website.manage"}
    assert permissions_for_role([config], "hub_admin") == {"website.view", "website.manage"}
    # The website speaks for the business: a manager sees it, only the owner and the admin change or publish it.
    assert permissions_for_role([config], "hub_manager") == {"website.view"}
    assert permissions_for_role([config], "hub_employee") == set()


# The assistant's contract: every operation is one of its tools (CLAUDE.md «Un solo camino hacia el servidor»).


def website_operations():
    from live.operations import registry

    return {name: op for name, op in registry.items() if name.startswith("website.")}


def test_the_operations_of_the_app():
    operations = website_operations()
    assert {name for name, op in operations.items() if op.kind == "query"} == {
        "website.site.get",
        "website.site.preview",
        "website.qr.get",
        "website.catalog.categories",
        "website.public.site",
        "website.public.catalog",
    }
    assert {name for name, op in operations.items() if op.kind == "command"} == {
        "website.site.save",
        "website.site.publish",
        "website.site.unpublish",
        "website.image.upload",
    }


def test_the_public_operations_need_no_permission_and_the_rest_do():
    operations = website_operations()
    public = {name for name, op in operations.items() if op.permission is None}
    assert public == {"website.public.site", "website.public.catalog"}
    assert {op.permission for name, op in operations.items() if name not in public} == {
        "website.view",
        "website.manage",
    }
    assert operations["website.site.get"].permission == "website.view"
    assert operations["website.qr.get"].permission == "website.view"
    for name in ("website.site.preview", "website.catalog.categories", "website.site.save", "website.site.publish", "website.site.unpublish", "website.image.upload"):
        assert operations[name].permission == "website.manage", name


#: What only the editor's screen calls, never the assistant: an HTML page (the preview), a file in base64 (an image's
#: upload, the QR's PNG or SVG) and the anonymous reads of the visitors' page. The assistant reads and changes the site
#: with the rest, as the person who asks (PLAN §14: every operation is a tool unless it cannot be one).
SCREEN_ONLY = {
    "website.site.preview",
    "website.image.upload",
    "website.qr.get",
    "website.public.site",
    "website.public.catalog",
}


def test_the_assistant_gets_every_operation_but_the_screen_only_ones():
    operations = website_operations()
    assert {name for name, op in operations.items() if op.ai is not None} == {
        "website.site.get",
        "website.site.save",
        "website.site.publish",
        "website.site.unpublish",
        "website.catalog.categories",
    }
    for name, op in operations.items():
        if name in SCREEN_ONLY:
            assert op.ai is None, name
            continue
        assert isinstance(op.ai, dict), name
        assert len(str(op.ai.get("description", "")).strip()) > 20, name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, name


def test_saving_tells_the_assistant_to_send_the_whole_draft_it_read():
    description = website_operations()["website.site.save"].ai["description"]
    # The save replaces the draft: what the assistant leaves out goes back to empty, so it reads it first.
    assert "website.site.get" in description and "whole" in description
    for word in ("template", "palette", "mode", "hours", "hidden"):
        assert word in description, word


def test_every_field_of_the_draft_is_described_for_the_assistant():
    from apps.website.schemas import SaveIn

    schema = SaveIn.model_json_schema()
    undescribed = [
        f"{model}.{name}"
        for model, definition in [("SaveIn", schema), *schema.get("$defs", {}).items()]
        for name, field in definition.get("properties", {}).items()
        if not str(field.get("description", "")).strip()
    ]
    assert undescribed == []
