"""Two devices at once (PRINTING-F18): real claims in threads, real row locks.

Two devices that claim at once never take the same job (``SELECT … FOR UPDATE SKIP LOCKED``); two requests
with the same key at once queue one job; two confirmations at once confirm it once. A read that a printer's
deletion lands in the middle of answers what it read or 404, never a 500; a write that names a printer holds
it, so the deletion waits for it, and one deleted before is not found.
"""

import threading
import time
from contextlib import contextmanager

import pytest
from django.db import connection, transaction
from live.errors import NotFound, OperationError

from apps.printing.models import Printer, PrintJob, Settings
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


# A printer deleted while it is being read or written to. The app never deletes one (it is deactivated), but
# the staff's admin can delete one without jobs. The reads found it and then loaded it again by its id (its
# queue, or the settings' chosen printer), so a deletion committed between the two raised DoesNotExist; the
# writes found it unlocked and saved a job or a choice that names it, which the database refused at the
# COMMIT (IntegrityError). Both were a 500. Each case lands the deletion there.

#: The admin's deletion gives up after this when a write holds the printer (a real one waits for its COMMIT).
ADMIN_LOCK_TIMEOUT = "500ms"
#: Postgres' ``lock_not_available``: the deletion found the printer held.
LOCK_NOT_AVAILABLE = "55P03"


def delete_as_the_admin(printer_id) -> None:
    """What the admin's «Delete» runs (``Printer.delete``), giving up when a write holds the printer."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{ADMIN_LOCK_TIMEOUT}'")
        Printer.objects.get(pk=printer_id).delete()


@contextmanager
def deleted_after_the_first_read_of(model, gone):
    """Deletes the printer ``gone`` as the admin does, in another session, right after the first statement
    of this one that reads from ``model``'s table: committed, or refused when this one already holds it."""
    table = f'FROM "{model._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete_as_the_admin(gone.id)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def held(deletions) -> bool:
    """The admin's deletion waited for the printer this write holds (and gave up)."""
    return len(deletions) == 1 and getattr(deletions[0].__cause__, "sqlstate", None) == LOCK_NOT_AVAILABLE


@pytest.mark.parametrize("ref", ["id", "name"])
@pytest.mark.parametrize("name", ["printing.printer.get", "printing.printer.status"])
def test_a_printer_deleted_while_it_is_read_is_never_a_server_error(name, ref):
    till = printer("Till")
    said = {"printer_id": str(till.id)} if ref == "id" else {"printer": "till"}
    with deleted_after_the_first_read_of(Printer, till) as deletions:
        read = run(name, said)
    assert deleted(deletions) == ["ok"]
    row = read if name == "printing.printer.get" else read.printer
    # The printer as it was read, with its queue.
    assert (row.id, row.name, row.state, row.pending) == (till.id, "Till", "ready", 0)
    # What runs next (a reload, the assistant asking again): not found, with the app's key.
    with pytest.raises(NotFound) as error:
        run(name, said)
    assert (error.value.code, error.value.status) == ("printing.printer_not_found", 404)


def test_the_chosen_printer_deleted_while_the_summary_is_read_is_never_a_server_error():
    till = printer("Till")
    run("printing.settings.update", {"receipt_printer": "Till"})
    with deleted_after_the_first_read_of(Settings, till) as deletions:
        summary = run("printing.job.summary")
    assert deleted(deletions) == ["ok"]
    receipts = next(row for row in summary.usages if row.usage == "receipt")
    # The settings as they were read, with their chosen printer.
    assert receipts.default_printer == "Till"
    # Read again: the admin's deletion cleared the choice.
    receipts = next(row for row in run("printing.job.summary").usages if row.usage == "receipt")
    assert (receipts.default_printer, receipts.printers) == (None, 0)


def test_a_printer_deleted_while_its_test_page_is_queued_waits_for_it():
    till = printer("Till")
    with deleted_after_the_first_read_of(Printer, till) as deletions:
        job = run("printing.printer.test", {"printer_id": str(till.id)})
    assert held(deletions), deleted(deletions)
    assert (job.printer_id, job.kind, job.status) == (till.id, "test_page", "pending")
    assert Printer.objects.filter(pk=till.id).exists()


@pytest.mark.parametrize("ref", ["id", "name"])
def test_a_printer_deleted_while_a_job_is_queued_on_it_waits_for_it(ref):
    till = printer("Till")
    said = str(till.id) if ref == "id" else "till"
    with deleted_after_the_first_read_of(Printer, till) as deletions:
        queued = enqueue(printer=said)
    assert held(deletions), deleted(deletions)
    assert (queued.job.printer_id, queued.job.status, queued.duplicate) == (till.id, "pending", False)
    assert Printer.objects.filter(pk=till.id).exists()


def test_a_printer_deleted_before_a_job_names_it_is_not_found():
    till = printer("Till")
    with deleted_after_the_first_read_of(Settings, till) as deletions:
        with pytest.raises(NotFound) as error:
            enqueue(printer="till")
    assert (deleted(deletions), error.value.code, error.value.status) == (["ok"], "printing.printer_not_found", 404)
    assert PrintJob.objects.count() == 0


def test_the_chosen_printer_deleted_while_a_receipt_is_queued_sends_it_to_another_of_its_function():
    till = printer("Till")
    spare = printer("Spare")
    run("printing.settings.update", {"receipt_printer": "Till"})
    with deleted_after_the_first_read_of(Settings, till) as deletions:
        queued = enqueue()
    assert deleted(deletions) == ["ok"]
    assert (queued.job.printer_id, queued.job.printer_name) == (spare.id, "Spare")


def test_a_printer_deleted_while_it_is_chosen_in_the_settings_waits_for_it():
    till = printer("Till")
    with deleted_after_the_first_read_of(Printer, till) as deletions:
        settings = run("printing.settings.update", {"receipt_printer": "Till"})
    assert held(deletions), deleted(deletions)
    assert settings.receipt_printer_id == till.id
    assert Settings.objects.get().receipt_printer_id == till.id


@pytest.mark.parametrize("chosen", [True, False])
def test_the_printer_a_receipt_goes_to_by_itself_deleted_while_it_is_queued_waits_for_it(chosen):
    till = printer("Till")
    if chosen:
        run("printing.settings.update", {"receipt_printer": "Till"})
    with deleted_after_the_first_read_of(Printer, till) as deletions:
        queued = enqueue()
    assert held(deletions), deleted(deletions)
    assert (queued.job.printer_id, queued.job.status) == (till.id, "pending")
    assert Printer.objects.filter(pk=till.id).exists()


# Two writes that name printers at once must never wait for each other in a circle (a deadlock is a 500). A
# write that names a printer holds it with a key-share lock, which the admin's deletion waits for but another
# write that names it does not: two rounds of paper on the same printers in any order, a round of paper while
# the owner changes a printer whose queue moves to another, or while the owner chooses one in the settings.

DEADLOCK = "40P01"


def sqlstate(result) -> str | None:
    return getattr(result, "sqlstate", None) or getattr(getattr(result, "__cause__", None), "sqlstate", None)


def paper(name: str, key: str):
    return enqueue(
        document_type="kitchen_order",
        usage="kitchen",
        printer=name,
        document={"ticket_id": "T-2", "items": [{"name": "Soup", "quantity": 1}]},
        job_key=key,
    )


def staggered(*calls):
    """Runs every ``call`` in its own thread and session, started together but paced by the calls themselves."""
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            results[index] = call()
        except Exception as error:  # reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_two_rounds_of_paper_on_the_same_printers_in_inverse_order_never_deadlock():
    printer("Kitchen", usage="kitchen")
    printer("Bar", usage="bar")
    both_hold_one = threading.Barrier(2)

    def round_of(first, second, tag):
        def go():
            with transaction.atomic():  # as Kitchen does: every sheet of a ticket in its own transaction
                one = paper(first, f"{tag}-1")
                both_hold_one.wait(5)
                time.sleep(0.3)
                two = paper(second, f"{tag}-2")
                return (one.job.printer_name, two.job.printer_name)

        return go

    results = staggered(round_of("Kitchen", "Bar", "a"), round_of("Bar", "Kitchen", "b"))
    assert [sqlstate(result) for result in results] == [None, None], results
    assert results == [("Kitchen", "Bar"), ("Bar", "Kitchen")]


def test_a_round_of_paper_while_a_printer_with_queue_is_deactivated_never_deadlocks():
    printer("Kitchen", usage="kitchen")
    printer("Kitchen 2", usage="kitchen")
    paper("Kitchen", "queued-on-kitchen")  # Kitchen's queue moves to Kitchen 2 when it is deactivated
    round_holds_kitchen_2 = threading.Event()

    def round_of_paper():
        with transaction.atomic():
            first = paper("Kitchen 2", "round-kitchen-2")
            round_holds_kitchen_2.set()
            time.sleep(0.6)  # the deactivation is under way
            second = paper("Kitchen", "round-kitchen")
            return (first.job.printer_name, second.job.printer_name)

    def deactivate():
        round_holds_kitchen_2.wait(5)
        return run("printing.printer.update", {"printer": "Kitchen", "is_active": False}).state

    results = staggered(round_of_paper, deactivate)
    assert [sqlstate(result) for result in results] == [None, None], results
    assert results[1] == "inactive"
    # The round either queued on Kitchen before it went inactive, or was refused: never a server error.
    assert results[0] == ("Kitchen 2", "Kitchen") or isinstance(results[0], OperationError), results[0]


def test_choosing_a_printer_while_its_function_is_changed_never_deadlocks():
    printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"kitchen_printer": "Kitchen"})
    settings_held = threading.Event()

    def choose():
        def pause_after_the_settings_are_read(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if sql.lstrip().upper().startswith("SELECT") and 'FROM "printing_settings"' in sql and not settings_held.is_set():
                settings_held.set()
                time.sleep(0.6)  # the change of function is under way
            return result

        with connection.execute_wrapper(pause_after_the_settings_are_read):
            return run("printing.settings.update", {"kitchen_printer": "Kitchen"}).kitchen_printer_id

    def change_function():
        settings_held.wait(5)
        return run("printing.printer.update", {"printer": "Kitchen", "usage": "bar"}).usage

    results = staggered(choose, change_function)
    assert [sqlstate(result) for result in results] == [None, None], results
    assert results[1] == "bar"
    # The choice either landed before the change (which then cleared it) or was refused: never a server error.
    assert isinstance(results[0], OperationError) or results[0] is not None, results[0]
