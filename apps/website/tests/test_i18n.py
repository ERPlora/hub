"""Every visible text of the website app has its Spanish translation, compiled and current: the store's texts, the
models, the errors and the public page's chrome (``{% translate %}`` in its templates)."""

import gettext
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.website import queries, schemas, services
from apps.website.models import Image, Site
from base.catalog import build_registry
from base.tests.po import catalogue_key, po_entries

APP = Path(apps.get_app_config("website").path)
LOCALE = APP / "locale" / "es" / "LC_MESSAGES"
TEMPLATES = APP / "templates" / "website"
_TRANSLATE = re.compile(r'{%\s*translate\s+"([^"]+)"(?:\s+context\s+"([^"]+)")?\s*%}')


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
        schemas.NOT_A_PLACE,
    ]
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies}


def template_texts() -> set[str]:
    found = set()
    for template in TEMPLATES.rglob("*.html"):
        for msgid, context in _TRANSLATE.findall(template.read_text(encoding="utf-8")):
            found.add(f"{context}\x04{msgid}" if context else msgid)
    return found


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [key for key, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


def test_every_visible_text_and_every_template_text_is_in_the_catalog():
    """By its whole key, context included: a text that goes back to ``_()`` while its entry keeps the context, or whose
    context has a typo, is missing from the catalogue — on screen it says another app's Spanish (hub#661)."""
    known = set(po_entries(LOCALE / "django.po"))
    texts = visible_texts()
    assert len({key for key in texts if "\x04" in key}) >= 5  # positive control: the contexts were kept
    assert texts - known == set()
    assert template_texts() and template_texts() - known == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {key: msgstr for key, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {key: value for key, value in catalog.items() if key} == po


def test_the_store_reads_the_name_with_its_context():
    """base.catalog reads the module's name in this catalogue as Django does, with its ``app name`` context: a plain
    «Website» entry would be Spanish only for the store, and the merged catalogue gives Clientes' «Web» to it."""
    [entry] = build_registry([apps.get_app_config("website")])
    assert (entry.name_en, entry.name_es) == ("Website", "Página web")
    assert "Website" not in po_entries(LOCALE / "django.po")


def test_spanish_says_the_websites_own_words_not_an_earlier_apps():
    """The texts Página web shares in English with an app loaded before it come out in Spanish with its own words
    (hub#661): the site and its images are feminine, «actualizada el», «actualizada por» and «creada el» like its
    «publicada el», not Demo's or Clientes' masculine; its form errors speak as its others do and as its WORKBOOK says
    («Escribe un correo electrónico válido.»), not Equipo's «Introduzca…»; and a site is «Página web», not Clientes'
    «Web»."""
    labels = {
        "Site.updated_at": Site._meta.get_field("updated_at").verbose_name,
        "Site.updated_by": Site._meta.get_field("updated_by").verbose_name,
        "Image.created_at": Image._meta.get_field("created_at").verbose_name,
        "NOT_AN_EMAIL": schemas.NOT_AN_EMAIL,
    }
    with translation.override("es"):
        assert {name: str(label) for name, label in labels.items()} | {"Site": str(Site())} == {
            "Site.updated_at": "actualizada el",
            "Site.updated_by": "actualizada por",
            "Image.created_at": "creada el",
            "NOT_AN_EMAIL": "Escribe un correo electrónico válido.",
            "Site": "Página web",
        }


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
