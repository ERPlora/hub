"""Every visible text of the online booking app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise

from apps.online_booking import queries, schemas, services
from apps.online_booking.models import Booking, Settings

LOCALE = Path(apps.get_app_config("online_booking").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, Booking)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``key → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped).

    The key is the msgid, or ``context\x04msgid`` for an entry with a ``msgctxt`` (gettext's own key).
    """
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        context = _unescape("".join(parts["msgctxt"]))
        if msgid:
            key = f"{context}\x04{msgid}" if context else msgid
            entries[key] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts_entry = (
            line.startswith("msgctxt ")
            or (line.startswith("msgid ") and current != "msgctxt")
            or (line.startswith("#") and current == "msgstr")
        )
        if starts_entry:
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


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top, alone or as the values of a dict."""
    found = []
    for value in vars(module).values():
        items = value.values() if isinstance(value, dict) else (value,)
        found += [item for item in items if isinstance(item, Promise)]
    return found


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages)."""
    config = apps.get_app_config("online_booking")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    with translation.override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 40  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("online_booking")
        assert str(config.verbose_name) == "Reservas online"
        assert [str(nav.label) for nav in config.navigation] == ["Reservas", "Ajustes"]
        assert str(queries.PAGE_DISABLED) == "Este negocio no acepta reservas online ahora mismo."
        assert str(queries.BOOKING_NOT_FOUND) == "Esa reserva no existe o su enlace ya no es válido."
        assert str(queries.DEFAULT_TITLE) == "Reserva tu cita"
        assert str(services.TIME_TAKEN) == "Esa hora ya no está libre. Elige otra."
        assert str(services.DEFAULT_CONFIRMED) == "Tu reserva está confirmada. ¡Hasta pronto!"


@pytest.mark.django_db
def test_the_public_page_answers_in_the_visitors_language(client, make_user, salon):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.get("/api/online_booking/public/page", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert response.json()["title"] == "Reserva tu cita"
    refused = client.get(
        "/api/online_booking/bookings/detail", {"number": "APT-NOPE"}, HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es"
    )
    assert refused.status_code == 404
    assert refused.json()["error"]["message"] == "Esa reserva no existe o su enlace ya no es válido."
    assert json.dumps(refused.json())
