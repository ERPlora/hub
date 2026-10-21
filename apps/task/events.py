"""Events of the task app (``task.<entity>.<fact>``) and its reaction to Staff's.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids (and a task's number or a project's code), never a title, a
description or a comment: free text that may name a customer or a colleague.

Reaction: a person who leaves the team (``staff.member.terminated``) leaves their open tasks without
an assignee, through an operation of this app run as the system, in its own transaction. The outbox
relay of the worker (``base.relay``) hands each event to ``react``; the operation is idempotent, so a
repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

TASK_CREATED = "task.task.created"
TASK_UPDATED = "task.task.updated"
TASK_STATUS_CHANGED = "task.task.status_changed"
TASK_COMPLETED = "task.task.completed"
TASK_ASSIGNED = "task.task.assigned"
TASK_DELETED = "task.task.deleted"
COMMENT_ADDED = "task.comment.added"
PROJECT_CREATED = "task.project.created"
PROJECT_UPDATED = "task.project.updated"
PROJECT_DELETED = "task.project.deleted"

ALL = [
    TASK_CREATED,
    TASK_UPDATED,
    TASK_STATUS_CHANGED,
    TASK_COMPLETED,
    TASK_ASSIGNED,
    TASK_DELETED,
    COMMENT_ADDED,
    PROJECT_CREATED,
    PROJECT_UPDATED,
    PROJECT_DELETED,
]

#: Everything that changes what a task row says (its project's name and colour included).
TASK_EVENTS = [
    TASK_CREATED,
    TASK_UPDATED,
    TASK_STATUS_CHANGED,
    TASK_COMPLETED,
    TASK_ASSIGNED,
    TASK_DELETED,
    COMMENT_ADDED,
]
PROJECT_EVENTS = [PROJECT_CREATED, PROJECT_UPDATED, PROJECT_DELETED]

# Staff's events (its WORKBOOK fixes the payload: ``{"id": …}``): a renamed or departed person changes
# the names a task row shows.
STAFF_MEMBER_UPDATED = "staff.member.updated"
STAFF_MEMBER_TERMINATED = "staff.member.terminated"
STAFF_MEMBER_EVENTS = [STAFF_MEMBER_UPDATED, STAFF_MEMBER_TERMINATED]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {STAFF_MEMBER_TERMINATED: "task.task.release_member"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
