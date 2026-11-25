"""Writes of the projects (TASK-F12–F14): create one with a code no other project has, edit it and delete it,
which leaves its tasks without a project."""

from uuid import UUID

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.task import events
from apps.task.models import Project
from apps.task.queries.projects import load_project
from apps.task.queries.reads import Caller
from apps.task.schemas import DeletedOut, ProjectIn, ProjectOut, ProjectPatchIn, ProjectRefIn
from apps.task.services.writes import _locked_project, _member

PROJECT_EXISTS = _("There is already a project with that code.")


def _project_exists() -> Conflict:
    return Conflict(str(PROJECT_EXISTS), code="task.project_exists", fields={"code": str(PROJECT_EXISTS)})


@operation(
    "task.project.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.manage_project",
    input=ProjectIn,
    output=ProjectOut,
    expose_api=True,
    ai={
        "description": "Create a project to group related tasks, with a unique code, a name and an "
        "optional colour and owner.",
        "risk": "normal",
        "asks": {
            "en": (
                "create a project called Refit with the code REF",
                "new task project Opening, in orange",
            ),
            "es": (
                "da de alta el proyecto Reformas, código REF",
                "nuevo proyecto de tareas Apertura, de color naranja",
            ),
        },
    },
)
def create_project(ctx: OperationContext, data: ProjectIn) -> dict:
    owner = _member(data.owner_id, data.owner, id_field="owner_id", name_field="owner")
    if Project.objects.filter(code__iexact=data.code).exists():
        raise _project_exists()
    try:
        with atomic():
            project = Project.objects.create(code=data.code, name=data.name, color=data.color, owner=owner)
    except IntegrityError:  # two saves of the same code at once: the code is the only unique field
        raise _project_exists() from None
    record_event(ctx, events.PROJECT_CREATED, {"id": str(project.pk), "code": project.code})
    return load_project(project.pk, Caller(ctx))


@operation(
    "task.project.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.manage_project",
    input=ProjectPatchIn,
    output=ProjectOut,
    expose_api=True,
    ai={
        "description": "Change a project's name, colour or owner, or take it out of use (is_active false) "
        "and back; only the fields sent change. The code never changes.",
        "risk": "normal",
        "check": "task.project.detail",
        "asks": {
            "en": (
                "rename the Opening project to Summer opening",
                "make the Refit project green",
            ),
            "es": (
                "cambia el nombre del proyecto Apertura a Apertura de verano",
                "pon el proyecto Reformas en verde",
            ),
        },
    },
)
def update_project(ctx: OperationContext, data: ProjectPatchIn) -> dict:
    sent = data.model_fields_set
    owner_sent = True
    if "owner" in sent and data.owner is not None:
        owner = _member(None, data.owner, id_field="owner_id", name_field="owner")
    elif "owner_id" in sent:
        owner = _member(data.owner_id, None, id_field="owner_id", name_field="owner")
    else:
        owner_sent, owner = False, None
    project = _locked_project(data.id, data.project)
    changes: dict = {}
    for field in ("name", "color", "is_active"):
        value = getattr(data, field)
        if field in sent and value is not None and value != getattr(project, field):
            changes[field] = value
    if owner_sent and (owner.pk if owner else None) != project.owner_id:
        changes["owner"] = owner
    if changes:
        for field, value in changes.items():
            setattr(project, field, value)
        project.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.PROJECT_UPDATED, {"id": str(project.pk)})
    return load_project(project.pk, Caller(ctx))


@operation(
    "task.project.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.manage_project",
    input=ProjectRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a project for good; its tasks stay, without a project.",
        "risk": "high",
        "check": "task.project.detail",
        "asks": {
            "en": (
                "delete the Opening project",
                "get rid of the Refit project but keep its tasks",
            ),
            "es": (
                "borra el proyecto Apertura",
                "elimina el proyecto Reformas y deja sus tareas sueltas",
            ),
        },
    },
)
def delete_project(ctx: OperationContext, data: ProjectRefIn) -> dict:
    project = _locked_project(data.id, data.project)
    payload = {"id": str(project.pk), "code": project.code}
    project.delete()
    record_event(ctx, events.PROJECT_DELETED, payload)
    return {"id": UUID(payload["id"])}
