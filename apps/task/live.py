"""Live queries of the task app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.task.events import (
    COMMENT_ADDED,
    PROJECT_CREATED,
    PROJECT_DELETED,
    PROJECT_UPDATED,
    STAFF_MEMBER_EVENTS,
    TASK_ASSIGNED,
    TASK_CREATED,
    TASK_DELETED,
    TASK_EVENTS,
    TASK_STATUS_CHANGED,
    TASK_UPDATED,
)

# A task row shows its project's name and colour and its assignee's name.
TASK_ROW = [*TASK_EVENTS, PROJECT_UPDATED, PROJECT_DELETED, *STAFF_MEMBER_EVENTS]
live("task.task.list", on=TASK_ROW)
live("task.task.mine", on=TASK_ROW)
live("task.task.detail", on=TASK_ROW)
live("task.task.subtasks", on=TASK_ROW)
# A reassignment may hide the task (and its thread) from an employee.
live("task.comment.list", on=[COMMENT_ADDED, TASK_ASSIGNED, TASK_DELETED])
# A project row counts its tasks (and the open ones) and names its owner.
PROJECT_ROW = [
    PROJECT_CREATED,
    PROJECT_UPDATED,
    PROJECT_DELETED,
    TASK_CREATED,
    TASK_UPDATED,
    TASK_STATUS_CHANGED,
    TASK_DELETED,
    *STAFF_MEMBER_EVENTS,
]
live("task.project.list", on=PROJECT_ROW)
live("task.project.detail", on=PROJECT_ROW)
