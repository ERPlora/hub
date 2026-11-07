"""Every visible text of the flow app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.flow import queries, recipes, schemas, services
from apps.flow.models import Draft, Flow, FlowRun, Question, Secret
from base.tests.po import po_entries

LOCALE = Path(apps.get_app_config("flow").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Flow, FlowRun, Draft, Secret, Question)


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("flow")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
        *module_texts(recipes),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (Flow.Trigger, FlowRun.Status, Draft.Status, Question.Status):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles flow's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones flow wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "flow"
        for field in op.input.model_fields.values()
        if field.title
    }


def untranslated(entries: dict[str, tuple[str, bool]]) -> list[str]:
    """The keys gettext shows in English: no ``msgstr``, or a ``#, fuzzy`` one it skips."""
    return [key for key, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    assert untranslated(entries) == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 60  # positive control: the collection found the app's texts
    msgids = {key.split("\x04")[-1] for key in po_entries(LOCALE / "django.po")}
    assert visible_texts() - msgids == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_flows_own_spanish():
    """A title flow shares with an app installed before it («Permissions» with Django's accounts) is said with that
    app's Spanish, so flow's own entry would be dead text: they have to say the same (hub#323)."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
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
