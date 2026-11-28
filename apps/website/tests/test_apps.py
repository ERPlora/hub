"""The website app declares its module metadata, its menu entry, its permissions and what each role gets."""

import pytest
from django.apps import apps
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role
from live.operations import INTERNAL

from base.tenancy.tests.business import HUB_DB
from base.tests import help_videos


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
    assert list(config.permissions) == ["website.view", "website.manage"]
    assert set(config.role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}
    assert permissions_for_role([config], "hub_owner") == {"website.view", "website.manage"}
    assert permissions_for_role([config], "hub_admin") == {"website.view", "website.manage"}
    # The website speaks for the business: a manager sees it, only the owner and the admin change or publish it.
    assert permissions_for_role([config], "hub_manager") == {"website.view"}
    assert permissions_for_role([config], "hub_employee") == set()


# The assistant's contract: every operation is one of its tools.


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
        "website.public.reviews",
        *CARD_ONLY,
        *EXPORT_ONLY,
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
    assert public == {"website.public.site", "website.public.catalog", "website.public.reviews"}
    assert {op.permission for name, op in operations.items() if name not in public} == {
        "website.view",
        "website.manage",
    }
    assert operations["website.site.get"].permission == "website.view"
    assert operations["website.qr.get"].permission == "website.view"
    for name in ("website.site.preview", "website.catalog.categories", "website.site.save", "website.site.publish", "website.site.unpublish", "website.image.upload"):
        assert operations[name].permission == "website.manage", name
    # An image is read by whoever sees the site; a category, as the editor's own list of them, by who changes it.
    assert operations["website.image.get"].permission == "website.view"
    assert operations["website.image.download"].permission == "website.view"
    assert operations["website.category.get"].permission == "website.manage"


#: What only the editor's screen calls, never the assistant: an HTML page (the preview), a file in base64 (an image's
#: upload, the QR's PNG or SVG) and the anonymous reads of the visitors' page. The assistant reads and changes the site
#: with the rest, as the person who asks (every operation is a tool unless it cannot be one).
#: What only the assistant's card reads, to name a record a save keeps: an image by the name of its file, a
#: category of the catalog by its name. No tool, no route, nothing live.
CARD_ONLY = {"website.image.get", "website.category.get"}
#: What only an export of the business reads, to carry each image of the page inside the file. No tool, no route.
EXPORT_ONLY = {"website.image.download"}
SCREEN_ONLY = {
    "website.site.preview",
    "website.image.upload",
    "website.qr.get",
    "website.public.site",
    "website.public.catalog",
    "website.public.reviews",
    *CARD_ONLY,
    *EXPORT_ONLY,
}


def test_the_assistant_gets_every_operation_but_the_screen_only_ones():
    operations = website_operations()
    assert {name for name, op in operations.items() if isinstance(op.ai, dict)} == {
        "website.site.get",
        "website.site.save",
        "website.site.publish",
        "website.site.unpublish",
        "website.catalog.categories",
    }
    for name, op in operations.items():
        if name in SCREEN_ONLY:
            assert op.ai is INTERNAL, name
            continue
        assert isinstance(op.ai, dict), name
        assert len(str(op.ai.get("description", "")).strip()) > 20, name
        # What a person types to ask for it (``asks``): website is listed in LIVE_ASSISTANT_ASKS_REQUIRED.
        expected = {"description", "asks", "risk"} if op.kind == "command" else {"description", "asks"}
        if name == "website.site.save":
            expected.add("summary")
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


def test_its_help_window_plays_the_app_s_tour_in_spanish_and_in_english():
    assert website().help.videos == {"es": "c_eaJUp0VQ4", "en": "k1rnkdX9GDU"}


#: The short video of each task, with the flows it shows: its Spanish and its English one.
TASK_VIDEOS = [
    (("WEBSITE-F01",), "JvaOnGvy-_s", "hLyBTFeITFc"),
    (("WEBSITE-F02",), "ivAQLYwuqRg", "lrgmUSOaICw"),
    (("WEBSITE-F03", "WEBSITE-F05"), "LADk7huQV5A", "LvUFTktstI4"),
    (("WEBSITE-F04", "WEBSITE-F11"), "CpHm3c5LpF8", "CJc3ij7WhNM"),
    (("WEBSITE-F07", "WEBSITE-F08", "WEBSITE-F10"), "tZQwXZW4fkM", "4PQ6LfGngyg"),
    (("WEBSITE-F09",), "gUnb_p6mwVc", "_hNFl4jyOLo"),
]


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_task_of_the_help_window_shows_its_short_videos_in_the_person_s_language(language):
    assert help_videos.shown("website", language) == help_videos.by_task(TASK_VIDEOS, language)
