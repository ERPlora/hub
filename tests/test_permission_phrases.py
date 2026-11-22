"""Every permission of the Hub's apps has its phrase, and Spanish reads it from the app's own catalogue.

An app declares its permissions as ``{permission: phrase}`` (``LiveAppConfig.permissions``): the phrase says in business
words what the permission lets a person do, the text a business reads beside each switch of a role. It is written in
English, as the source of i18n, and its Spanish lives in the app's own ``locale/es/LC_MESSAGES/django.po``, compiled.
What Spanish shows is compared with that entry, so a phrase left out of the catalogue, not compiled, fuzzy, or that an
earlier app translates otherwise (Django keeps the first app's words) fails here, naming the permission.
"""

from collections.abc import Mapping
from pathlib import Path

from django.conf import settings
from django.utils import translation
from live.meta import all_live_app_configs

from base.tests.po import catalogue_key, po_entries

SPANISH = Path("locale", "es", "LC_MESSAGES", "django.po")


def hub_configs() -> list:
    """The apps of the Hub's own code that declare permissions: ``base`` and every module."""
    root = Path(settings.BASE_DIR).resolve()
    return [
        config
        for config in all_live_app_configs()
        if config.permissions and Path(config.path).resolve().is_relative_to(root)
    ]


def phrases() -> list[tuple[object, str, object]]:
    """``(app, permission, phrase)`` of every permission of the Hub's apps; one declared without its phrase (a list) has
    ``None``."""
    return [
        (config, permission, config.permissions[permission] if isinstance(config.permissions, Mapping) else None)
        for config in hub_configs()
        for permission in config.permissions
    ]


def test_base_and_every_module_are_read():
    labels = {config.label for config in hub_configs()}

    assert "base" in labels
    assert len(labels) > 25, f"only {sorted(labels)} declare permissions: the checks below would read too few"
    assert len(phrases()) > 180


def test_every_app_declares_its_permissions_with_their_phrases():
    assert [config.label for config in hub_configs() if not isinstance(config.permissions, Mapping)] == []


def test_spanish_reads_every_phrase_from_its_own_catalogue():
    wrong = []
    catalogues: dict[str, dict] = {}
    for config, permission, phrase in phrases():
        if phrase is None:
            wrong.append(f"{permission}: no phrase")
            continue
        entries = catalogues.setdefault(config.label, po_entries(Path(config.path) / SPANISH))
        with translation.override("en"):
            key = catalogue_key(phrase)
        own, fuzzy = entries.get(key, ("", False))
        with translation.override("es"):
            said = str(phrase)
        if not own or fuzzy or said != own:
            wrong.append(f"{permission}: {key!r} says «{said}», its catalogue «{own}»{' (fuzzy)' if fuzzy else ''}")
    assert wrong == []
