"""Reads of a task's comments (TASK-F10): its thread, the newest first, with the author of each comment."""

from live.context import OperationContext
from live.operations import operation

from apps.task.models import Comment
from apps.task.queries.reads import Caller, _page, resolve_task, user_name
from apps.task.schemas import CommentListIn, CommentPage


def comment_row(comment: Comment) -> dict:
    return {
        "id": comment.pk,
        "task_id": comment.task_id,
        "text": comment.text,
        "author_id": comment.author_id,
        "author_name": user_name(comment.author),
        "created_at": comment.created_at,
    }


@operation(
    "task.comment.list",
    kind="query",
    permission="task.view",
    input=CommentListIn,
    output=CommentPage,
    expose_api=True,
    ai={
        "description": "Lists the comments of a task (by id, number or title), the newest first.",
        "asks": {
            "en": (
                "what comments are there on the task paint the front?",
                "read me the comment thread of task TSK-0042",
            ),
            "es": (
                "¿qué comentarios tiene la tarea de pintar la fachada?",
                "léeme el hilo de comentarios de la TSK-0042",
            ),
        },
    },
)
def list_comments(ctx: OperationContext, params: CommentListIn) -> dict:
    task = resolve_task(Caller(ctx), params.task_id, params.task)
    comments = Comment.objects.filter(task=task).select_related("author").order_by("-created_at", "-id")
    return _page(comments, params, comment_row)
