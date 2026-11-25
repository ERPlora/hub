"""Reads of the projects (TASK-F13): the list, with the owner of each project and how many of its tasks (and open
ones) the caller sees, one project by what the caller calls it, and the row a write answers with."""

from uuid import UUID

from django.db.models import Count, Q, QuerySet
from live.context import OperationContext
from live.operations import operation

from base.ordering import list_order_for
from apps.task.models import Project, Task
from apps.task.queries.reads import VIEW_ALL, Caller, _full_name, _page, resolve_project
from apps.task.schemas import ProjectListIn, ProjectOut, ProjectPage, ProjectRefIn


# The model columns behind each sort key of the schemas.
PROJECT_ORDER = {
    "code": ("code",),
    "name": ("name",),
    "color": ("color",),
    "is_active": ("is_active",),
    "owner_name": ("owner_name",),
    "task_count": ("task_count",),
    "open_task_count": ("open_task_count",),
    "created_at": ("created_at",),
    "id": (),
}


def annotated_projects(projects: QuerySet[Project], caller: Caller) -> QuerySet[Project]:
    """Projects with their owner's name and how many tasks (and open ones) the caller sees in them."""
    seen = Q() if caller.ctx.has(VIEW_ALL) else caller.own("tasks__")
    return projects.annotate(
        owner_name=_full_name("owner"),
        task_count=Count("tasks", filter=seen, distinct=True),
        open_task_count=Count("tasks", filter=seen & ~Q(tasks__status__in=Task.CLOSED), distinct=True),
    )


def project_row(project: Project) -> dict:
    return {
        "id": project.pk,
        "code": project.code,
        "name": project.name,
        "color": project.color,
        "is_active": project.is_active,
        "owner_id": project.owner_id,
        "owner_name": project.owner_name,
        "task_count": project.task_count,
        "open_task_count": project.open_task_count,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def load_project(project_id: UUID, caller: Caller) -> dict:
    return project_row(annotated_projects(Project.objects.filter(pk=project_id), caller).get())


@operation(
    "task.project.list",
    kind="query",
    permission="task.view",
    input=ProjectListIn,
    output=ProjectPage,
    expose_api=True,
    ai={
        "description": "Lists the task projects with their code, colour, whether they are active and how "
        "many tasks (and open tasks) each one has.",
        "asks": {
            "en": (
                "which task projects do we have?",
                "list the active projects",
            ),
            "es": (
                "¿qué proyectos tenemos?",
                "lista los proyectos activos",
            ),
        },
    },
)
def list_projects(ctx: OperationContext, params: ProjectListIn) -> dict:
    projects = annotated_projects(Project.objects.all(), Caller(ctx))
    if params.search:
        projects = projects.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    if params.code:
        projects = projects.filter(code__icontains=params.code)
    if params.name:
        projects = projects.filter(name__icontains=params.name)
    if params.color:
        projects = projects.filter(color__icontains=params.color)
    if params.is_active is not None:
        projects = projects.filter(is_active=params.is_active)
    if params.owner_id:
        projects = projects.filter(owner_id=params.owner_id)
    ordered = projects.order_by(*list_order_for(params.sort, columns=PROJECT_ORDER, nulls_last=True))
    return _page(ordered, params, project_row)


@operation(
    "task.project.detail",
    kind="query",
    permission="task.view",
    input=ProjectRefIn,
    output=ProjectOut,
    expose_api=True,
    ai={
        "description": "Returns one task project, by id, by its code or by its name.",
        "asks": {
            "en": (
                "show me the Opening project",
                "what colour is the Refit project and who runs it?",
            ),
            "es": (
                "enséñame el proyecto Apertura del local",
                "¿de qué color es el proyecto Reformas y quién lo lleva?",
            ),
        },
    },
)
def project_detail(ctx: OperationContext, data: ProjectRefIn) -> dict:
    rows = annotated_projects(Project.objects.all(), Caller(ctx))
    return project_row(resolve_project(data.id, data.project, rows=rows))
