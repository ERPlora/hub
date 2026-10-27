"""Every visible text of the kitchen app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.operations import registry

from apps.kitchen import queries, schemas, services
from apps.kitchen.models import (
    CategoryRoute,
    DayCounter,
    Destination,
    ItemStatus,
    KitchenSettings,
    LogAction,
    LogEntry,
    OrderType,
    PrinterUsage,
    Priority,
    ProductRoute,
    SoundTone,
    Station,
    Ticket,
    TicketItem,
    TicketStatus,
)

LOCALE = Path(apps.get_app_config("kitchen").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (
    Station,
    ProductRoute,
    CategoryRoute,
    KitchenSettings,
    DayCounter,
    Ticket,
    TicketItem,
    LogEntry,
)
CHOICES = (
    Destination,
    PrinterUsage,
    OrderType,
    Priority,
    SoundTone,
    TicketStatus,
    ItemStatus,
    LogAction,
)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped)."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            context = _unescape("".join(parts["msgctxt"]))
            entries[f"{context}\x04{msgid}" if context else msgid] = (
                _unescape("".join(parts["msgstr"])),
                fuzzy,
            )

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = line.startswith("msgctxt ") or (
            line.startswith("msgid ") and current != "msgctxt"
        )
        if starts_entry or (line.startswith("#") and current == "msgstr"):
            flush()
            parts, fuzzy, current = (
                {"msgctxt": [], "msgid": [], "msgstr": []},
                False,
                None,
            )
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def lazy_constants(module) -> list:
    return [
        value for value in vars(module).values() if type(value).__name__ == "__proxy__"
    ]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages, paper) and the
    titles of its schemas."""
    config = apps.get_app_config("kitchen")
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
    for choices in CHOICES:
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles kitchen's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones kitchen wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "kitchen"
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
    entries = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - entries == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("kitchen")
        assert str(config.verbose_name) == "Cocina"
        assert [str(nav.label) for nav in config.navigation] == [
            "Pantalla",
            "Comandas",
            "Estaciones",
            "Historial",
        ]
        assert str(services.INVALID_TRANSITION) == (
            "Esa comanda ya no está en el estado que requiere esta acción. Actualiza e inténtalo de nuevo."
        )
        assert (
            str(services.STATION_NAME_TAKEN)
            == "Ya hay una estación con ese nombre. Elige otro nombre."
        )
        assert (
            str(services.STATION_INACTIVE)
            == "Esa estación está desactivada: actívala o elige otra."
        )
        assert (
            str(services.AMBER_FIRST)
            == "El aviso ámbar tiene que llegar antes que el rojo."
        )
        assert str(services.URGENT) == "!! URGENTE !!"
        assert (
            str(services.VOIDED_DISH) % {"label": "Mesa 4"} == "PLATO ANULADO · Mesa 4"
        )
        assert str(queries.TICKET_NOT_FOUND) == "Esa comanda no existe en este negocio."
        assert [str(label) for label in TicketStatus.labels] == [
            "Por preparar",
            "En preparación",
            "Lista",
            "Servida",
            "Cancelada",
        ]
        assert [str(label) for label in OrderType.labels] == [
            "En sala",
            "Para llevar",
            "A domicilio",
        ]
        assert [str(label) for label in Priority.labels] == ["Normal", "Urgente", "VIP"]


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/kitchen/stations/delete",
        json.dumps({"station": "Nowhere"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"] == "Esa estación no existe en este negocio."
    )
