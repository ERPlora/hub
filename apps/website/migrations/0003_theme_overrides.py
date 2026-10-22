"""The website's theme: «Your colours» stops being a palette of its own (round 2026-10-22, W8).

Any palette now takes the owner's two colours over its own (``theme.custom``; null = the palette's colours). A theme
``{palette: "custom", custom: {primary, accent}}`` becomes ``ocean`` with the same two colours, painted exactly as
before (the page is derived from them whatever the palette), and the colours a curated palette only kept for a later
«Your colours» go: they were never painted, and now they would be. The draft and the publication change alike; an
empty theme is left alone. The reverse turns a palette with the owner's colours back into the custom palette, which
painted them the same. Only the JSON changes.
"""

from django.db import migrations

#: The palette a custom one becomes: the default (any would do: the owner's colours decide the page).
BASE = "ocean"


def _to_overrides(theme):
    if not isinstance(theme, dict) or "palette" not in theme:
        return None
    if theme["palette"] == "custom":
        return {**theme, "palette": BASE}
    if theme.get("custom") is not None:
        return {**theme, "custom": None}
    return None


def _to_custom_palette(theme):
    if not isinstance(theme, dict) or not theme.get("custom") or theme.get("palette") == "custom":
        return None
    return {**theme, "palette": "custom"}


def _convert(apps, schema_editor, change):
    rows = apps.get_model("website", "Site").objects.using(schema_editor.connection.alias)
    for site in rows.only("pk", "theme", "published_content"):
        changes = {}
        theme = change(site.theme)
        if theme is not None:
            changes["theme"] = theme
        published = site.published_content or {}
        published_theme = change(published.get("theme"))
        if published_theme is not None:
            changes["published_content"] = {**published, "theme": published_theme}
        if changes:
            rows.filter(pk=site.pk).update(**changes)


def to_overrides(apps, schema_editor):
    _convert(apps, schema_editor, _to_overrides)


def to_custom_palette(apps, schema_editor):
    _convert(apps, schema_editor, _to_custom_palette)


class Migration(migrations.Migration):
    dependencies = [("website", "0002_theme_palettes")]

    operations = [migrations.RunPython(to_overrides, to_custom_palette)]
