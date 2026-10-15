"""Two devices at once (PRINTING-F18): real claims in threads, real row locks.

Two devices that claim at once never take the same job (``SELECT … FOR UPDATE SKIP LOCKED``); two requests
with the same key at once queue one job; two confirmations at once confirm it once.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import RECEIPT, enqueue, printer, run

pytestmark = pytest.mark.django_db(transaction=True)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_two_devices_at_once_take_two_different_jobs():
    till = printer("Till")
    enqueue(source_ref="T-1")
    enqueue(source_ref="T-2")
    claim = lambda device: lambda: run("printing.job.claim", {"printers": [str(till.id)], "device": device}).job  # noqa: E731
    first, second = at_once(claim("A"), claim("B"))
    assert first is not None and second is not None, (first, second)
    assert first.id != second.id
    assert PrintJob.objects.filter(status="sent").count() == 2


def test_the_same_key_at_once_is_one_job():
    ask = lambda: run(  # noqa: E731
        "printing.job.create", {"job_key": "sale-1-receipt", "document_type": "receipt", "document": RECEIPT}
    )
    results = at_once(ask, ask, ask)
    assert all(not isinstance(result, Exception) for result in results), results
    assert len({result.job.id for result in results}) == 1
    assert sorted(result.duplicate for result in results) == [False, True, True]
    assert PrintJob.objects.count() == 1


def test_two_confirmations_at_once_confirm_once():
    till = printer("Till")
    queued = enqueue().job
    run("printing.job.claim", {"printers": [str(till.id)], "device": "A"})
    done = lambda: run("printing.job.complete", {"job_id": str(queued.id), "device": "A", "attempt": 1})  # noqa: E731
    results = at_once(done, done)
    assert [result.confirmed for result in results] == [True, True]
    assert PrintJob.objects.get(pk=queued.id).status == "done"
