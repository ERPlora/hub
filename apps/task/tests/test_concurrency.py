"""Two people at once: real sessions in threads, real row locks (WORKBOOK «Para quien lo mantiene»).

Two tasks created at the same moment get consecutive numbers, never the same one; two completions of
the same task close it once and the second one is told it was already closed.
"""

import threading

import pytest
from django.db import connection
from django.utils import timezone
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import get

from apps.task.models import Task

from .conftest import ctx_for, make_task

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # an expected refusal or an unexpected failure, both reported
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_tasks_created_at_once_get_consecutive_numbers():
    results = at_once(*(lambda n=n: run("task.task.create", {"title": f"T{n}"}) for n in range(4)))
    day = timezone.localdate().strftime("%Y%m%d")
    assert sorted(result.number for result in results) == [f"TSK-{day}-{n:04d}" for n in range(1, 5)]


def test_two_completions_of_the_same_task_close_it_once():
    task = make_task()
    results = at_once(*(lambda: run("task.task.complete", {"id": str(task.id)}) for _ in range(2)))
    refused = [result for result in results if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "task.task_already_closed"
    assert Task.objects.get(pk=task.pk).status == "done"
    assert OutboxEvent.objects.filter(name="task.task.completed").count() == 1
