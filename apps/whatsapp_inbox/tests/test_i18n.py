"""Every visible text of the WhatsApp inbox has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils.functional import Promise
from django.utils.translation import override

from apps.whatsapp_inbox import queries, schemas, services
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import receive

LOCALE = (
    Path(apps.get_app_config("whatsapp_inbox").path) / "locale" / "es" / "LC_MESSAGES"
)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``key → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped).

    The key is the msgid, or ``context\x04msgid`` for an entry with a ``msgctxt``, as the compiled
    catalog keys it.
    """
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
        starts = line.startswith("msgctxt ") or (line.startswith("msgid ") and current != "msgctxt")
        if starts or (line.startswith("#") and current == "msgstr"):
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


def msgids(path: Path) -> set[str]:
    """The English sources of the catalog, without their contexts."""
    return {key.split("\x04", 1)[-1] for key in po_entries(path)}


def module_texts(module) -> list:
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, errors)."""
    config = apps.get_app_config("whatsapp_inbox")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(schemas),
        *module_texts(queries),
        *module_texts(services),
    ]
    for model in (Channel, Conversation, Message, Note, Template):
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    for choices in (
        Channel.Status,
        Conversation.Status,
        Message.Direction,
        Message.Origin,
        Message.Source,
        Message.Status,
        Template.Category,
        Template.Status,
        Template.HeaderFormat,
        Template.SubmitState,
        Template.DeleteState,
    ):
        lazies += list(choices.labels)
    with override("en"):
        return {str(text) for text in lazies}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [
        msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy
    ] == []


def test_every_visible_text_is_in_the_catalog():
    assert visible_texts() - msgids(LOCALE / "django.po") == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts():
    with override("es"):
        assert (
            str(apps.get_app_config("whatsapp_inbox").verbose_name)
            == "Bandeja de WhatsApp"
        )
        assert str(Conversation.Status.PENDING.label) == "Pendiente"
        assert str(Message.Status.READ.label) == "Leído"
        assert str(Template.Status.DELETED.label) == "Borrada en WhatsApp Manager"
        assert str(services.WINDOW_CLOSED) == (
            "Han pasado más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja escribirle "
            "con una plantilla aprobada."
        )


@pytest.mark.django_db
def test_an_error_follows_the_language_of_the_request(client, make_user):
    receive("wamid.1")
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/whatsapp_inbox/messages/send",
        json.dumps({"conversation": "Zoe", "text": "Hola", "client_message_id": "0199e000-0000-7000-8000-0000000000be"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Ninguna conversación coincide con «Zoe»."
    )
