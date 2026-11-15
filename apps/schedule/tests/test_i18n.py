"""Every visible text of the schedule app has its Spanish translation, compiled and current."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation

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
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    missing_from_catalogue,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
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


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, messages, day names) and the titles
    of its schemas."""
    config = apps.get_app_config("schedule")
    lazies = [
        *config_texts(config),
        # The Home's step.
        *(text for step in config.setup for text in (step.title, step.description)),
        *models.WEEKDAY_NAMES,
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("schedule")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Horarios by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=40, with_context=6) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_schedules_own_spanish():
    """A title schedule shares with an app installed before it would be said with that app's Spanish, and schedule's
    own entry would be dead text: they have to say the same, or the card's word would hang on the order of the
    apps."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("schedule")
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
