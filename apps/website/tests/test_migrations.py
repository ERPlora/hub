"""Migrations 0002 and 0003 of the website app's theme (round 2026-10-22).

0002: the two free colours of before become the custom palette.

A site's draft theme and the theme of its publication ``{primary, accent, mode}`` become ``{palette: "custom",
custom: {primary, accent}, mode}``, so every page keeps its colours; a theme already in the new shape and an empty one
are left alone. The reverse gives back the two colours (a curated palette's own, for a site that chose one) and turns
``auto`` into ``light``.

0003: «Your colours» stops being a palette of its own: any palette takes the owner's two colours over its own
(``custom``), so a custom palette becomes ``ocean`` with its colours (painted the same), and the colours a curated
palette kept for later go (they were not painted). The reverse turns a palette with the owner's colours back into the
custom palette. The functions of the ``RunPython`` are called the way the migrations run them.
"""

import uuid
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.website.models import Site
from apps.website.palettes import PALETTES
from apps.website.schemas import Theme

pytestmark = pytest.mark.django_db

migration = import_module("apps.website.migrations.0002_theme_palettes")
overrides = import_module("apps.website.migrations.0003_theme_overrides")

OLD = {"primary": "#aa0000", "accent": "#112233", "mode": "dark"}
NEW = {"palette": "custom", "custom": {"primary": "#aa0000", "accent": "#112233"}, "mode": "dark"}


def site(theme: dict, published_theme: dict | None = None) -> Site:
    published = {} if published_theme is None else {"template": "modern", "theme": published_theme, "content": {}}
    return Site.objects.create(hub_id=uuid.uuid4(), theme=theme, published_content=published)


def run(function) -> None:
    with connection.schema_editor() as editor:
        function(global_apps, editor)


def test_the_two_colours_become_the_custom_palette_in_the_draft_and_the_publication():
    old = site(OLD, {"primary": "#2563eb", "accent": "#f59e0b", "mode": "light"})
    run(migration.to_palettes)
    old.refresh_from_db()
    assert old.theme == NEW
    assert old.published_content["theme"] == {
        "palette": "custom",
        "custom": {"primary": "#2563eb", "accent": "#f59e0b"},
        "mode": "light",
    }
    assert old.published_content["template"] == "modern"
    # What it writes is, once 0003 has run, a valid theme of today with the same colours.
    run(overrides.to_overrides)
    old.refresh_from_db()
    assert Theme.model_validate(old.theme).custom.primary == "#aa0000"


def test_a_theme_already_moved_or_empty_and_a_site_never_published_are_left_alone():
    moved = site({"palette": "forest", "custom": None, "mode": "auto"})
    empty = site({})
    never = site(OLD)
    run(migration.to_palettes)
    for row in (moved, empty, never):
        row.refresh_from_db()
    assert moved.theme == {"palette": "forest", "custom": None, "mode": "auto"}
    assert empty.theme == {}
    assert never.theme == NEW and never.published_content == {}


def test_the_reverse_gives_back_two_colours_and_a_light_or_dark_page():
    custom = site(NEW, NEW)
    curated = site({"palette": "forest", "custom": None, "mode": "auto"})
    run(migration.to_colours)
    custom.refresh_from_db()
    curated.refresh_from_db()
    assert custom.theme == OLD and custom.published_content["theme"] == OLD
    assert curated.theme == {"primary": PALETTES["forest"]["light"]["primary"], "accent": PALETTES["forest"]["accent"], "mode": "light"}


def test_the_migration_runs_its_python_both_ways():
    operation = migration.Migration.operations[0]
    assert operation.code is migration.to_palettes
    assert operation.reverse_code is migration.to_colours


TWEAK = {"primary": "#aa0000", "accent": "#112233"}


def test_the_custom_palette_becomes_ocean_with_the_owners_colours_and_kept_colours_go():
    custom = site({"palette": "custom", "custom": TWEAK, "mode": "dark"}, {"palette": "custom", "custom": TWEAK, "mode": "auto"})
    kept = site({"palette": "forest", "custom": TWEAK, "mode": "auto"}, {"palette": "sand", "custom": TWEAK, "mode": "light"})
    plain = site({"palette": "forest", "custom": None, "mode": "auto"})
    empty = site({})
    run(overrides.to_overrides)
    for row in (custom, kept, plain, empty):
        row.refresh_from_db()
    assert custom.theme == {"palette": "ocean", "custom": TWEAK, "mode": "dark"}
    assert custom.published_content["theme"] == {"palette": "ocean", "custom": TWEAK, "mode": "auto"}
    assert custom.published_content["template"] == "modern"
    # Colours a curated palette only kept for later were never painted: they go, and the page stays as it was.
    assert kept.theme == {"palette": "forest", "custom": None, "mode": "auto"}
    assert kept.published_content["theme"] == {"palette": "sand", "custom": None, "mode": "light"}
    assert plain.theme == {"palette": "forest", "custom": None, "mode": "auto"} and plain.published_content == {}
    assert empty.theme == {}
    for row in (custom, kept, plain):
        Theme.model_validate(row.theme)


def test_the_reverse_turns_the_owners_colours_back_into_the_custom_palette():
    tweaked = site({"palette": "forest", "custom": TWEAK, "mode": "auto"}, {"palette": "forest", "custom": TWEAK, "mode": "dark"})
    plain = site({"palette": "forest", "custom": None, "mode": "auto"})
    run(overrides.to_custom_palette)
    tweaked.refresh_from_db()
    plain.refresh_from_db()
    assert tweaked.theme == {"palette": "custom", "custom": TWEAK, "mode": "auto"}
    assert tweaked.published_content["theme"] == {"palette": "custom", "custom": TWEAK, "mode": "dark"}
    assert plain.theme == {"palette": "forest", "custom": None, "mode": "auto"}


def test_migration_0003_runs_its_python_both_ways():
    operation = overrides.Migration.operations[0]
    assert overrides.Migration.dependencies == [("website", "0002_theme_palettes")]
    assert operation.code is overrides.to_overrides
    assert operation.reverse_code is overrides.to_custom_palette

