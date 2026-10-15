"""Ninja routes of the task app: each route calls exactly one operation and holds no logic.

No path parameters: ids (or a task's number or title, a project's code or name) travel in the input
(query string on GET, body on POST), because a route takes one parameter, the operation's input. The
platform's reaction (``release_member``) has no route: no person and no API key reaches it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.task import queries, services
from apps.task.schemas import (
    AssignIn,
    CommentIn,
    CommentListIn,
    ProjectIn,
    ProjectListIn,
    ProjectPatchIn,
    ProjectRefIn,
    SetStatusIn,
    SubtaskListIn,
    TaskIn,
    TaskListIn,
    TaskMineIn,
    TaskPatchIn,
    TaskRefIn,
)

router = Router(tags=["task"])


# Tasks


@bind(router, "task.task.list", "/task/tasks")
async def task_list(request, params: Query[TaskListIn]):
    return await run_operation(request, queries.list_tasks, params)


@bind(router, "task.task.mine", "/task/tasks/mine")
async def task_mine(request, params: Query[TaskMineIn]):
    return await run_operation(request, queries.my_tasks, params)


@bind(router, "task.task.detail", "/task/tasks/detail")
async def task_detail(request, params: Query[TaskRefIn]):
    return await run_operation(request, queries.task_detail, params)


@bind(router, "task.task.subtasks", "/task/tasks/subtasks")
async def task_subtasks(request, params: Query[SubtaskListIn]):
    return await run_operation(request, queries.list_subtasks, params)


@bind(router, "task.task.create", "/task/tasks", status=201)
async def task_create(request, data: TaskIn):
    return await run_operation(request, services.create_task, data)


@bind(router, "task.task.update", "/task/tasks/update")
async def task_update(request, data: TaskPatchIn):
    return await run_operation(request, services.update_task, data)


@bind(router, "task.task.set_status", "/task/tasks/set_status")
async def task_set_status(request, data: SetStatusIn):
    return await run_operation(request, services.set_status, data)


@bind(router, "task.task.complete", "/task/tasks/complete")
async def task_complete(request, data: TaskRefIn):
    return await run_operation(request, services.complete_task, data)


@bind(router, "task.task.assign", "/task/tasks/assign")
async def task_assign(request, data: AssignIn):
    return await run_operation(request, services.assign_task, data)


@bind(router, "task.task.delete", "/task/tasks/delete")
async def task_delete(request, data: TaskRefIn):
    return await run_operation(request, services.delete_task, data)


# Comments


@bind(router, "task.comment.list", "/task/comments")
async def comment_list(request, params: Query[CommentListIn]):
    return await run_operation(request, queries.list_comments, params)


@bind(router, "task.comment.add", "/task/comments", status=201)
async def comment_add(request, data: CommentIn):
    return await run_operation(request, services.add_comment, data)


# Projects


@bind(router, "task.project.list", "/task/projects")
async def project_list(request, params: Query[ProjectListIn]):
    return await run_operation(request, queries.list_projects, params)


@bind(router, "task.project.detail", "/task/projects/detail")
async def project_detail(request, params: Query[ProjectRefIn]):
    return await run_operation(request, queries.project_detail, params)


@bind(router, "task.project.create", "/task/projects", status=201)
async def project_create(request, data: ProjectIn):
    return await run_operation(request, services.create_project, data)


@bind(router, "task.project.update", "/task/projects/update")
async def project_update(request, data: ProjectPatchIn):
    return await run_operation(request, services.update_project, data)


@bind(router, "task.project.delete", "/task/projects/delete")
async def project_delete(request, data: ProjectRefIn):
    return await run_operation(request, services.delete_project, data)
