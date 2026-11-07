"""Every visible text of the task app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation

from apps.task import queries, schemas, services
from apps.task.models import Comment, Project, Task, TaskCounter
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

LOCALE = Path(apps.get_app_config("task").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (Project, Task, Comment, TaskCounter)


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("task")
    lazies = [
        *config_texts(config),
        *module_texts(queries, services, schemas),
    ]
    lazies += model_texts(MODELS)
    for choices in (Task.Status, Task.Priority):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("task")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """Each text of Tareas by its whole key, context included: a ``pgettext_lazy`` that goes back to ``_()``, or
    whose context has a typo, is missing from the catalogue, and Spanish says it in English (hub#975)."""
    assert missing_from_catalogue(visible_texts(), LOCALE / "django.po", more_than=40, with_context=9) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_tasks_own_spanish():
    """A title task shares with another app («Assigned to» with the WhatsApp inbox) is said with the Spanish of the
    one that comes first in ``INSTALLED_APPS`` (today task) and the other's entry is dead text: they have to say the
    same, or the card's word would hang on the order of the apps."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("task")
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
