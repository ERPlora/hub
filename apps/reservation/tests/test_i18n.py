"""Every visible text of the reservation app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

from apps.reservation import queries, schemas, services
from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)

LOCALE = Path(apps.get_app_config("reservation").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Settings, TimeSlot, BlockedDate, Reservation, WaitlistEntry)
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
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("reservation")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
    ]
    lazies += lazy_constants(queries) + lazy_constants(services) + lazy_constants(schemas)
    lazies += [message for message, _field in services.REFUSALS.values()]
    lazies += list(services.TARGET_WORDS.values())
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (Reservation.Status, Reservation.Source):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | {"Reservation settings"}


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy] == []


#: Texts Reservas shows but Customers owns (its reason for a phone that is not a number of its country, RESERVATION-F06):
#: they are translated once, in Customers' catalog.
BORROWED = (services.PHONE_INVALID,)
CUSTOMER_LOCALE = Path(apps.get_app_config("customer").path) / "locale" / "es" / "LC_MESSAGES"


def test_every_visible_text_is_in_the_catalog():
    with translation.override("en"):
        borrowed = {str(text) for text in BORROWED}
    assert visible_texts() - borrowed - msgids(po_entries(LOCALE / "django.po")) == set()
    assert borrowed - msgids(po_entries(CUSTOMER_LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_of_the_workbook():
    with translation.override("es"):
        config = apps.get_app_config("reservation")
        assert str(config.verbose_name) == "Reservas"
        assert [str(nav.label) for nav in config.navigation] == ["Reservas", "Lista de espera", "Disponibilidad"]
        assert [str(label) for label in Reservation.Status.labels] == [
            "Pendiente",
            "Confirmada",
            "Sentada",
            "Completada",
            "Cancelada",
            "No presentada",
        ]
        assert [str(label) for label in Reservation.Source.labels] == [
            "Teléfono",
            "En el local",
            "Lista de espera",
            "WhatsApp",
            "Internet",
        ]
        messages = {code: str(message) for code, (message, _field) in services.REFUSALS.items()}
        assert messages["phone_required"] == "Este negocio pide un teléfono en cada reserva."
        assert messages["date_blocked"] == (
            "Esa fecha está bloqueada (festivo o cierre): ese día no se aceptan reservas."
        )
        assert messages["outside_schedule"] == "A esa hora el negocio está cerrado."
        assert messages["no_service_day"] == "No hay servicio a esa hora: ninguna franja la cubre."
        assert messages["no_capacity"] == "Esa franja ya está completa para ese día."
        assert str(services.NOT_EDITABLE) == "Esta reserva ya no se puede cambiar: solo sus notas."
        assert str(services.ENTRY_CONVERTED) == "Esta entrada ya se convirtió en reserva."


def test_a_refusal_names_the_status_in_spanish():
    with translation.override("es"):
        label = str(Reservation.Status.CONFIRMED.label).lower()
        assert str(services.STEP_REFUSED) % {"status": label, "target": services.TARGET_WORDS["confirmed"]} == (
            "Esta reserva está confirmada: no se puede confirmar."
        )


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/reservation/reservations/confirm",
        json.dumps({"guest": "Nadie"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa reserva no existe en este negocio."
