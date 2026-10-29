"""Every visible text of the schedule app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.schedule import models, queries, schemas, services
from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)

LOCALE = Path(apps.get_app_config("schedule").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (
    WeekDay,
    WeekDayInterval,
    SpecialDay,
    SpecialDayInterval,
    Override,
    OverrideInterval,
    ScheduleSettings,
)
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


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages, day names) and the titles
    of its schemas."""
    config = apps.get_app_config("schedule")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *models.WEEKDAY_NAMES,
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name")
            and not field.auto_created
            and not field.primary_key
        ]
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles schedule's operations give their input data (``gettext_noop``): the assistant's card names each
    datum by them, so each one needs its Spanish. Only the ones schedule wrote: pydantic leaves ``title`` empty
    otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "schedule"
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
    assert (
        len(visible_texts()) > 40
    )  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {
        msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()
    }
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_schedules_own_spanish():
    """A title schedule shares with an app installed before it would be said with that app's Spanish, and schedule's
    own entry would be dead text: they have to say the same, or the card's word would hang on the order of the
    apps."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
    assert {"Opening intervals", "Special days"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("schedule")
        assert str(config.verbose_name) == "Horarios"
        assert [str(nav.label) for nav in config.navigation] == [
            "Horario",
            "Días especiales",
            "Ajustes",
        ]
        assert [str(name) for name in models.WEEKDAY_NAMES] == [
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
            "Domingo",
        ]
        assert (
            str(schemas.MISSING_HOURS)
            == "Un día abierto necesita al menos un tramo horario."
        )
        assert str(schemas.OVERLAPPING) == (
            "Dos tramos se solapan (o uno cruza la medianoche sobre otro); ajusta las horas para que no se pisen."
        )
        assert (
            str(schemas.RANGE_BACKWARDS)
            == "La fecha de fin no puede ser anterior a la de inicio."
        )
        assert (
            str(services.SPECIAL_DAY_EXISTS)
            == "Ya existe un día especial en esa fecha."
        )
        assert (
            str(queries.SPECIAL_DAY_NOT_FOUND)
            == "Ese día especial no existe en este negocio."
        )


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(
            re.findall(r"%\(\w+\)s", msgstr)
        ), msgid


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/schedule/special_days/delete",
        json.dumps({"special_day": "Easter"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Ese día especial no existe en este negocio."
    )
