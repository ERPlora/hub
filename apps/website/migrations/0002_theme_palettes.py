"""The website's theme: from two free colours to a palette (round 2026-10-22).

The draft's theme and the publication's ``{primary, accent, mode}`` become ``{palette: "custom", custom: {primary,
accent}, mode}``: every page keeps its colours, now as the owner's own palette. A theme already in the new shape and an
empty one (the defaults: ocean, auto) are left alone. The reverse gives back two colours (a curated palette's main and
second colour, as they were when this migration was written) and a light page for ``auto``. Only the JSON changes.
"""

from django.db import migrations

#: The curated palettes' main (light) and second colour on the day of this migration, for the reverse.
CURATED = {
    "ocean": ("#0b5cad", "#f4b942"),
    "forest": ("#1f6b45", "#e3b04b"),
    "terracotta": ("#a8401f", "#2f6f73"),
    "slate": ("#334155", "#2fb7b0"),
    "rose": ("#b0305c", "#f6c1d0"),
    "sand": ("#8a5a24", "#2e6b5e"),
    "midnight": ("#3b3fb5", "#f5c84c"),
    "olive": ("#55641c", "#b9482f"),
}
OLD_KEYS = {"primary", "accent"}


def _to_palette(theme):
    if not isinstance(theme, dict) or not OLD_KEYS <= set(theme):
        return None
    return {
        "palette": "custom",
        "custom": {"primary": theme["primary"], "accent": theme["accent"]},
        "mode": theme.get("mode", "light"),
    }


def _to_colours(theme):
    if not isinstance(theme, dict) or "palette" not in theme:
        return None
    custom = theme.get("custom") or {}
    if theme["palette"] == "custom" and custom:
        primary, accent = custom["primary"], custom["accent"]
    else:
        primary, accent = CURATED.get(theme["palette"], CURATED["ocean"])
    mode = theme.get("mode", "light")
    return {"primary": primary, "accent": accent, "mode": mode if mode in ("light", "dark") else "light"}


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


def to_palettes(apps, schema_editor):
    _convert(apps, schema_editor, _to_palette)


def to_colours(apps, schema_editor):
    _convert(apps, schema_editor, _to_colours)


class Migration(migrations.Migration):
    dependencies = [("website", "0001_initial")]

    operations = [migrations.RunPython(to_palettes, to_colours)]
