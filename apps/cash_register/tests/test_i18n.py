"""Every visible text of the cash register app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise

from apps.cash_register import models, queries, schemas, services

LOCALE = (
    Path(apps.get_app_config("cash_register").path) / "locale" / "es" / "LC_MESSAGES"
)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped); an entry with a
    context is keyed ``context\x04msgid``, as gettext keys it in the compiled catalog."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            context = _unescape("".join(parts["msgctxt"]))
            key = f"{context}\x04{msgid}" if parts["msgctxt"] else msgid
            entries[key] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if (line.startswith(("msgctxt ", "msgid ")) and parts["msgid"]) or (
            line.startswith("#") and current == "msgstr"
        ):
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


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows: menu, store, admin, choices and messages."""
    config = apps.get_app_config("cash_register")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    for module in (queries, services, schemas, models):
        lazies += [
            value for value in vars(module).values() if isinstance(value, Promise)
        ]
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
        *models.Session.Status.labels,
        *models.Movement.Type.labels,
        *models.Count.Type.labels,
        *(label for _, label, _ in services.REPORT_LINES),
    ]
    with translation.override("en"):
        return {source(text) for text in lazies}


def source(text) -> str:
    """How the catalog keys a lazy text: its English, or ``context\x04English`` for a ``pgettext_lazy``."""
    args = getattr(text, "_args", ())
    return f"{args[0]}\x04{args[1]}" if len(args) == 2 else str(text)


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with translation.override("es"):
        assert str(apps.get_app_config("cash_register").verbose_name) == "Caja"
        assert (
            str(services.SESSION_ALREADY_OPEN)
            == "Ya hay una sesión de caja abierta. Ciérrala antes de abrir otra."
        )
        assert str(models.Movement.Type.OUT.label) == "Salida"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/cash_register/movements",
        json.dumps({"type": "in", "amount": 100}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "cash_register.no_open_session",
        "message": "No hay ninguna sesión de caja abierta: abre una primero.",
    }
