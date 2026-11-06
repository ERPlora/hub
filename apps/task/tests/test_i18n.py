"""Every visible text of the task app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.task import queries, schemas, services
from apps.task.models import Comment, Project, Task, TaskCounter
from base.tests.po import catalogue_key, po_entries

LOCALE = Path(apps.get_app_config("task").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Project, Task, Comment, TaskCounter)


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("task")
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
    for choices in (Task.Status, Task.Priority):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles task's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones task wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "task"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 40  # positive control: the collection found the app's texts
    assert visible_texts() - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_the_card_says_each_title_with_tasks_own_spanish():
    """A title task shares with another app («Assigned to» with the WhatsApp inbox) is said with the Spanish of the
    one that comes first in ``INSTALLED_APPS`` (today task) and the other's entry is dead text: they have to say the
    same, or the card's word would hang on the order of the apps."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = schema_titles()
    assert {"Assigned to", "Assign to me"} <= titles
    with translation.override("es"):
        assert {title: translation.gettext(title) for title in titles} == {
            title: own.gettext(title) for title in titles
        }


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("task")
        assert str(config.verbose_name) == "Tareas"
        assert [str(nav.label) for nav in config.navigation] == ["Tareas", "Proyectos"]
        assert [str(label) for label in Task.Status.labels] == [
            "Por hacer",
            "En curso",
            "Bloqueada",
            "Hecha",
            "Cancelada",
        ]
        assert [str(label) for label in Task.Priority.labels] == ["Baja", "Media", "Alta", "Urgente"]
        assert str(queries.TASK_NOT_FOUND) == "Esa tarea no existe en este negocio."
        assert str(queries.PROJECT_NOT_FOUND) == "Ese proyecto no existe en este negocio."
        assert str(services.TASK_ALREADY_CLOSED) == "Esa tarea ya está cerrada, así que se ha dejado como estaba."


def test_a_task_s_labels_are_feminine_and_a_project_s_masculine():
    """«Creada por», «Creada el» and «Actualizada el», as the sheet and the WORKBOOK say a task, with the task's own
    context: Inventario's «creado por» would otherwise speak for it (hub#666), and the project's masculine «creado el»
    is said by the same English."""
    with translation.override("es"):
        labels = {
            model: {field.name: str(field.verbose_name) for field in model._meta.fields}
            for model in MODELS
        }
    task = ("assigned_to", "created_by", "completed_at", "created_at", "updated_at")
    assert {name: labels[Task][name] for name in task} == {
        "assigned_to": "asignada a",
        "created_by": "creada por",
        "completed_at": "completada el",
        "created_at": "creada el",
        "updated_at": "actualizada el",
    }
    assert (labels[Project]["created_at"], labels[Project]["updated_at"], labels[Comment]["created_at"]) == (
        "creado el",
        "actualizado el",
        "creado el",
    )


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid
