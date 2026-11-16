"""Every visible text of the flow app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.flow import queries, recipes, schemas, services
from apps.flow.models import Draft, Flow, FlowRun, Question, Secret
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

LOCALE = Path(apps.get_app_config("flow").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Flow, FlowRun, Draft, Secret, Question)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("flow")
    lazies = [
        *config_texts(config),
        *module_texts(queries, services, schemas, recipes),
    ]
    lazies += model_texts(MODELS)
    for choices in (Flow.Trigger, FlowRun.Status, Draft.Status, Question.Status):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("flow")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Automatizaciones by its whole key, context included (hub#975): a ``pgettext_lazy`` that goes
    back to ``_()``, or whose context has a typo, is missing from the catalogue, and Spanish says it in English."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=140, with_context=15) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_flows_own_spanish():
    """A title flow shares with an app installed before it («Permissions» with Django's accounts) is said with that
    app's Spanish, so flow's own entry would be dead text: they have to say the same (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("flow")
    assert {"Permissions", "Starts with", "Actor"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("flow")
        assert str(config.verbose_name) == "Automatizaciones"
        assert [str(nav.label) for nav in config.navigation] == ["Automatizaciones"]
        assert [str(label) for label in Flow.Trigger.labels] == [
            "Pasa algo",
            "Según un horario",
            "Una vez, en una fecha y hora",
            "Solo a mano",
        ]
        assert str(services.UNTITLED) == "Automatización sin nombre"
        assert str(services.DISABLED) == "Esta automatización está en pausa: enciéndela para ejecutarla."
        assert str(queries.FLOW_NOT_FOUND) == "Esa automatización no existe en este negocio."


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid


def test_each_record_says_its_dates_and_authors_with_flows_own_words():
    """«Automatización», «ejecución» and «pregunta» are feminine and «borrador» and «secreto» masculine; an app installed
    before flow that says the same English («created at» in demo, «started at» in attendance, «step» in sale) spoke for
    flow's own Spanish (hub#497)."""
    said = {
        Flow: ("created_at", "created_by", "updated_at", "updated_by", "deleted_at"),
        FlowRun: ("started_at",),
        Question: ("step_id",),
        Draft: ("created_at", "created_by"),
        Secret: ("created_at", "created_by", "updated_at", "updated_by"),
    }
    with translation.override("es"):
        labels = {
            f"{model.__name__}.{name}": str(model._meta.get_field(name).verbose_name)
            for model, names in said.items()
            for name in names
        }
    assert labels == {
        "Flow.created_at": "creada el",
        "Flow.created_by": "creada por",
        "Flow.updated_at": "cambiada el",
        "Flow.updated_by": "cambiada por",
        "Flow.deleted_at": "borrada el",
        "FlowRun.started_at": "empezó el",
        "Question.step_id": "paso",
        "Draft.created_at": "creado el",
        "Draft.created_by": "creado por",
        "Secret.created_at": "creado el",
        "Secret.created_by": "creado por",
        "Secret.updated_at": "actualizado el",
        "Secret.updated_by": "actualizado por",
    }
