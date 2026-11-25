"""Writes of a task's comments (TASK-F10): a comment is added to the thread, signed by whoever writes it."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.task import events
from apps.task.models import Comment
from apps.task.queries import Caller, comment_row
from apps.task.schemas import CommentIn, CommentOut
from apps.task.services.writes import _changeable
from base.services.sessions import acting_hub_user

@operation(
    "task.comment.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.change",
    input=CommentIn,
    output=CommentOut,
    expose_api=True,
    ai={
        "description": "Add a comment to a task's thread, signed by the caller.",
        "risk": "normal",
        "asks": {
            "en": (
                "comment on the boiler task that the technician comes on Monday",
                "leave a comment on task TSK-0042: waiting for parts",
            ),
            "es": (
                "comenta en la tarea de la caldera que el técnico viene el lunes",
                "deja un comentario en la TSK-0042: faltan piezas",
            ),
        },
    },
)
def add_comment(ctx: OperationContext, data: CommentIn) -> dict:
    author = acting_hub_user(ctx)
    caller = Caller(ctx)
    task = _changeable(caller, data.task_id, data.task)
    comment = Comment.objects.create(task=task, author=author, text=data.text)
    record_event(ctx, events.COMMENT_ADDED, {"id": str(comment.pk), "task_id": str(task.pk)})
    return comment_row(comment)
