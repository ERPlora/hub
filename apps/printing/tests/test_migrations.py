"""Migration 0005 of the printing app: the kitchen orders waiting for a printer their function does not have are
cancelled.

Before it, Kitchen queued its orders even where no active printer prints their function (a kitchen that cooks from
its screen): they waited for nobody, rang the bell's «Nothing is printing» and would all come out at once the day a
printer of that function was added. The migration cancels them as the queue's «Cancel» does, letting their paper go;
what an active printer of its function can still print, the other papers and the jobs that ended are left alone.
Backwards it changes nothing: those orders were cooked from the screen.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry and a schema
editor whose connection is business A's own database, inside the test's transaction.
"""

from importlib import import_module

from django.apps import apps as global_apps
from django.db import connections

from apps.printing.models import PrintJob
from base.tenancy.context import current_alias

from .conftest import HUB_DB, enqueue, printer, run

pytestmark = HUB_DB

MIGRATION = import_module("apps.printing.migrations.0005_cancel_kitchen_orders_without_printer")

ITEM = {"name": "Burger", "quantity": 1}


class _SchemaEditor:
    @property
    def connection(self):
        return connections[current_alias()]


def kitchen_order(usage: str = "kitchen") -> PrintJob:
    """A kitchen order queued as Kitchen queued it, waiting for a printer of ``usage``."""
    queued = enqueue("kitchen_order", {"items": [ITEM]}, usage=usage, source_app="kitchen", source_ref="20261118-0001")
    return PrintJob.objects.get(pk=queued.job.id)


def state(job: PrintJob) -> tuple:
    job.refresh_from_db()
    return job.status, job.cancelled_at is not None, job.document


def test_the_kitchen_orders_no_active_printer_of_their_function_prints_are_cancelled():
    printer("Till")
    kitchen, bar = kitchen_order(), kitchen_order("bar")
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert state(kitchen) == ("cancelled", True, {})
    assert state(bar) == ("cancelled", True, {})


def test_an_inactive_printer_of_their_function_does_not_keep_them():
    grill = printer("Grill printer", usage="kitchen", address="10.0.0.2")
    run("printing.printer.update", {"printer_id": str(grill.id), "is_active": False})
    job = kitchen_order()
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert state(job)[0] == "cancelled"


def test_the_orders_an_active_printer_of_their_function_can_print_stay_in_the_queue():
    job = kitchen_order()
    queued = job.document
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert state(job) == ("pending", False, queued)
    assert queued["items"] == [ITEM]


def test_an_order_sent_to_a_printer_by_name_stays_on_it_with_no_printer_of_its_function():
    printer("Till")
    queued = enqueue("kitchen_order", {"items": [ITEM]}, usage="bar", printer="Till", source_app="kitchen")
    job = PrintJob.objects.get(pk=queued.job.id)
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert (state(job)[:2], job.printer.name) == (("pending", False), "Till")


def test_the_other_papers_and_the_jobs_that_ended_are_not_touched():
    receipt = PrintJob.objects.get(pk=enqueue(source_app="sale").job.id)
    failed = kitchen_order()
    PrintJob.objects.filter(pk=failed.pk).update(status="failed")
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert (state(receipt)[:2], state(failed)[:2]) == (("pending", False), ("failed", False))


def test_backwards_changes_nothing():
    job = kitchen_order()
    MIGRATION.backwards(global_apps, _SchemaEditor())
    assert state(job)[0] == "pending"
