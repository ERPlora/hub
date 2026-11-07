"""Every visible text of the attendance app has its Spanish translation, compiled and current, and the
short labels carry a context so another app's catalogue never translates them its own way."""

import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from django.utils.translation import gettext_lazy
from live.meta import Nav

from apps.attendance import queries, schemas, services
from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from base.tests.po import catalogue_key as source
from base.tests.po import (
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
)

LOCALE = Path(apps.get_app_config("attendance").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Record, Break, Correction, AttendanceSettings)


def visible_texts() -> set[str]:
    """The catalogue key of every lazy text the app shows (menu, store, admin, choices, messages)."""
    config = apps.get_app_config("attendance")
    lazies = [
        *config_texts(config),
        *(panel.title for panel in config.widgets),
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    for choices in (Record.Status, Record.Source):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {source(text) for text in lazies} | operation_titles("attendance")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def missing_from_catalog() -> set[str]:
    """The visible texts the catalogue has no entry for, each compared by its whole key."""
    return missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=60, with_context=9)


def test_every_visible_text_is_in_the_catalog():
    assert missing_from_catalog() == set()


def test_a_text_that_loses_its_context_is_missing_from_the_catalog(monkeypatch):
    """A label put back without its context while the catalogue keeps only the contexted entry: gettext never finds
    that entry, so Spanish says another app's words, or the English if no app has it (hub#493). The guard above has to
    fail on it. The message goes in a variable because ``makemessages`` would take a literal for a text of the app."""
    message = "Records"
    label = gettext_lazy(message)
    config = apps.get_app_config("attendance")
    monkeypatch.setattr(config, "navigation", [Nav("records", label, "ion:list-outline", "/attendance/records")])
    assert missing_from_catalog() == {message}


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("attendance")
        assert str(config.verbose_name) == "Control horario"
        assert [str(nav.label) for nav in config.navigation] == ["Fichar", "Registros"]
        assert [str(panel.title) for panel in config.widgets] == ["Fichados ahora"]
        assert [str(label) for label in Record.Status.labels] == ["Abierta", "Cerrada", "Por revisar"]
        assert str(services.ALREADY_IN) == "Ya tienes una jornada abierta: ficha la salida antes de volver a entrar."
        assert str(services.OVERLAP) == "Estas horas se solapan con otra jornada de esta persona."
        assert str(schemas.OUT_BEFORE_IN) == "La salida tiene que ser posterior a la entrada."
        assert str(services.OUTSIDE_RADIUS) % {"distance": 850, "radius": 100} == (
            "Estás a 850 m del lugar de trabajo, fuera de los 100 m permitidos. Acércate para fichar o ficha "
            "en el mostrador."
        )
        assert str(queries.TERMINATED_REASON) == "Jornada cerrada al dar de baja a la persona en Personal."


def test_short_labels_carry_their_context():
    # «Open», «Closed», «Clock in» and «Records» are words other apps translate their own way.
    entries = po_entries(LOCALE / "django.po")
    for key in (
        "working day status\x04Open",
        "working day status\x04Closed",
        "working day status\x04Needs review",
        "attendance menu\x04Clock in",
        "attendance menu\x04Records",
    ):
        assert key in entries, key


def said_in_spanish(key: str) -> str:
    """How the Hub says a catalogue entry in Spanish: every app's catalogue merged, the first one to have it winning."""
    with translation.override("es"):
        if "\x04" in key:
            context, msgid = key.split("\x04", 1)
            return translation.pgettext(context, msgid)
        return translation.gettext(key)


def test_no_other_apps_catalogue_says_a_text_of_attendance_its_own_way():
    """Staff's «working day» is a weekday of a schedule («día de trabajo»), attendance's the legal day («jornada»): an
    entry another catalogue also has, without its own context, was said the other app's way."""
    entries = po_entries(LOCALE / "django.po")
    assert len(entries) > 60  # positive control: the catalogue was read
    shadowed = {key: said_in_spanish(key) for key, (msgstr, _) in entries.items() if said_in_spanish(key) != msgstr}
    assert shadowed == {}


def test_a_working_day_is_a_jornada_in_spanish_and_a_working_day_in_english():
    """What the models call the day, the end of a break and the settings' slot: their admin and every screen or card
    that names a datum by its model (the assistant's card, an automation's fields) say them as attendance does."""
    names = lambda: [  # noqa: E731
        str(Record._meta.verbose_name),
        str(Record._meta.verbose_name_plural),
        str(Break._meta.get_field("record").verbose_name),
        str(Correction._meta.get_field("record").verbose_name),
        str(Break._meta.get_field("ended_at").verbose_name),
        str(AttendanceSettings._meta.get_field("slot").verbose_name),
    ]
    with translation.override("es"):
        assert names() == ["jornada", "jornadas", "jornada", "jornada", "terminó a las", "hueco"]
    with translation.override("en"):
        assert names() == ["working day", "working days", "working day", "working day", "ended at", "slot"]


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.get(
        "/api/attendance/records/detail",
        {"id": "0199c8a0-0000-7000-8000-000000000000"},
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa jornada no existe en este negocio."
    assert json.loads(response.content)["error"]["code"] == "not_found"
