"""Every visible text of the website app has its Spanish translation, compiled and current: the store's texts, the
models, the errors and the public page's chrome (``{% translate %}`` in its templates)."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.website import queries, schemas, services
from apps.website.models import Image, Site

APP = Path(apps.get_app_config("website").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"
TEMPLATES = APP / "templates" / "website"
_TRANSLATE = re.compile(r'{%\s*translate\s+"([^"]+)"(?:\s+context\s+"([^"]+)")?\s*%}')


def po_entries() -> dict[str, str]:
    """``"<context>\\x04<msgid>"`` (or ``"<msgid>"``) → msgstr; a fuzzy entry maps to ``""``."""
    entries: dict[str, str] = {}
    parts: dict[str, list[str]] = {}
    fuzzy, current = False, None

    def flush():
        msgid = "".join(parts.get("msgid", []))
        if msgid:
            context = "".join(parts.get("msgctxt", []))
            entries[f"{context}\x04{msgid}" if context else msgid] = "" if fuzzy else "".join(parts.get("msgstr", []))

    for line in (LOCALE / "django.po").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(("msgctxt ", "#")) or (line.startswith("msgid ") and current != "msgctxt"):
            if current == "msgstr":
                flush()
                parts, fuzzy = {}, False
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current] = [json.loads(rest)]
        elif line.startswith('"') and current:
            parts[current].append(json.loads(line))
    if current == "msgstr":
        flush()
    return entries


def visible_texts() -> set[str]:
    config = apps.get_app_config("website")
    lazies = [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]
    for model in (Site, Image):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    lazies += list(Site.Template.labels)
    lazies += [
        queries.NOT_PUBLISHED,
        queries.MODULE_OFF,
        services.IMAGE_NOT_FOUND,
        services.NOT_BASE64,
        services.EMPTY_FILE,
        services.TOO_HEAVY,
        services.NOT_THAT_TYPE,
        services.TOO_LARGE,
        schemas.NOT_HTTPS,
        schemas.NOT_A_PHONE,
        schemas.NOT_AN_EMAIL,
        schemas.SAME_TIMES,
        schemas.DAY_TWICE,
    ]
    with translation.override("en"):
        return {str(text) for text in lazies}


def template_texts() -> set[str]:
    found = set()
    for template in TEMPLATES.rglob("*.html"):
        for msgid, context in _TRANSLATE.findall(template.read_text(encoding="utf-8")):
            found.add(f"{context}\x04{msgid}" if context else msgid)
    return found


def test_every_entry_has_a_spanish_translation():
    entries = po_entries()
    assert entries
    assert [key for key, msgstr in entries.items() if not msgstr] == []


def test_every_visible_text_and_every_template_text_is_in_the_catalog():
    known = set(po_entries())
    assert visible_texts() - known == set()
    assert template_texts() and template_texts() - known == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    assert {key: value for key, value in catalog.items() if key} == po_entries()


def test_the_store_reads_the_name_without_a_context():
    # base.catalog looks the module's name up in this catalogue as plain gettext (register_apps).
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)
    assert catalog.gettext("Website") == "Página web"


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("website").verbose_name) == "Página web"
        assert str(queries.NOT_PUBLISHED) == "Esta página web no está publicada."
        assert not hasattr(schemas, "CUSTOM_WITHOUT_COLOURS")



@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client):
    response = client.get("/api/website/public/site", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esta página web no está publicada."
