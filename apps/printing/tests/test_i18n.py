"""Every visible text of the printing app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.printing import documents, models, queries, schemas, services

LOCALE = Path(apps.get_app_config("printing").path) / "locale" / "es" / "LC_MESSAGES"
TEMPLATE = Path(apps.get_app_config("printing").path) / "templates" / "printing" / "test_page.html"
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals or contexts (the header is skipped)."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            entries[msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("msgid ") or (line.startswith("#") and current == "msgstr"):
            flush()
            parts, fuzzy, current = {"msgid": [], "msgstr": []}, False, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, admin, choices, messages and the titles
    of its schemas."""
    config = apps.get_app_config("printing")
    lazies = [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]
    for module in (queries, services, schemas, models, documents):
        lazies += [value for value in vars(module).values() if isinstance(value, Promise)]
    for model in config.get_models():
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
            and isinstance(field.verbose_name, Promise)
        ]
    lazies += [
        *models.Usage.labels,
        *models.Printer.Kind.labels,
        *models.Printer.Paper.labels,
        *models.PrintJob.Kind.labels,
        *models.PrintJob.Format.labels,
        *models.PrintJob.Status.labels,
    ]
    with translation.override("en"):
        texts = {str(text) for text in lazies}
    texts |= set(re.findall(r'{% translate "([^"]+)" %}', TEMPLATE.read_text()))
    return texts | schema_titles()


def schema_titles() -> set[str]:
    """The titles printing's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones printing wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "printing"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("printing").verbose_name) == "Impresión"
        assert str(models.PrintJob.Status.FAILED.label) == "Fallido"
        assert str(services.PRINTER_EXISTS) == "Ya hay una impresora con ese nombre."


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/printing/printers",
        json.dumps({"name": "Caja", "kind": "network", "address": "no es una ip", "usage": "receipt"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "address": "Escribe una IP o un nombre de red válidos (por ejemplo 192.168.1.100)."
    }
