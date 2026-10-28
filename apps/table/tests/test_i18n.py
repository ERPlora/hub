"""Every visible text of the table app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.table import queries, schemas, services
from apps.table.models import (
    Hold,
    SessionMove,
    Table,
    TableSession,
    TableSettings,
    Zone,
)

LOCALE = Path(apps.get_app_config("table").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (TableSettings, Zone, Table, TableSession, SessionMove, Hold)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped). An entry with a
    context is keyed ``context\x04msgid``, as gettext compiles it."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            context = _unescape("".join(parts["msgctxt"]))
            entries[f"{context}\x04{msgid}" if context else msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgctxt ") or (line.startswith("msgid ") and current != "msgctxt")
        if starts_entry or (line.startswith("#") and current == "msgstr"):
            flush()
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, False, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def msgids(entries) -> set[str]:
    return {key.split("\x04")[-1] for key in entries}


def lazy_constants(module) -> list:
    """Every module-level lazy text (``_("…")``) of ``module``."""
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("table")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += (
        lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    )
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    for choices in (
        Zone.Color,
        Table.Shape,
        TableSession.Status,
        SessionMove.Reason,
        SessionMove.Release,
        Hold.Source,
        Hold.Status,
    ):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | {"Table %(number)s"} | schema_titles()


def schema_titles() -> set[str]:
    """The titles table's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones table wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "table"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - msgids(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("table")
        assert str(config.verbose_name) == "Mesas"
        assert [str(nav.label) for nav in config.navigation] == [
            "Plano de sala",
            "Zonas",
            "Mesas",
            "Sesiones",
        ]
        assert str(services.TABLE_HAS_OPEN_SESSION) == (
            "Esa mesa tiene una cuenta abierta. Ciérrala o trasládala antes de borrar la mesa."
        )
        assert (
            str(services.ZONE_HAS_TABLES)
            == "Esta zona todavía tiene mesas. Muévelas a otra zona o bórralas antes."
        )
        assert str(services.BILL_OPEN) == (
            "La cuenta de esta mesa sigue abierta en Ventas: cóbrala, pásala a otra mesa o elimínala desde el TPV."
        )
        assert (
            str(services.NUMBER_TAKEN) == "Ya hay una mesa con ese número en esta zona."
        )
        assert str(queries.TABLE_NOT_FOUND) == "Esa mesa no existe en este negocio."
        assert [str(label) for label in TableSession.Status.labels] == [
            "Abierta",
            "Cerrada",
            "Trasladada",
            "Fusionada",
            "Aparcada",
        ]
        assert [str(label) for label in Zone.Color.labels] == [
            "Azul",
            "Cian",
            "Morado",
            "Verde",
            "Ámbar",
            "Rojo",
            "Gris",
        ]


def test_a_tables_check_is_titled_in_spanish_for_a_spanish_waiter():
    with translation.override("es"):
        assert translation.gettext("Table %(number)s") % {"number": "4"} == "Mesa 4"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/table/zones/delete",
        json.dumps({"zone": "Nowhere"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa zona no existe en este negocio."
