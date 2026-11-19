"""Whether the station of a function answers now (``printing.device.health``): the Home's health row and System's «Your
printer» read it. A station answers when a device set up here reaches an active printer of the function on receipt
paper and gave news in the last 90 s; set up but quiet, it has no signal; with no such device, it is not set up."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import PermissionDenied

from apps.printing.models import PrintDevice
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, run
from apps.printing.tests.test_queries import reaches

pytestmark = HUB_DB


def health(usage: str = "receipt", ctx=None) -> str:
    out = run("printing.device.health", {"usage": usage}, ctx=ctx)
    assert out.usage == usage
    return out.state


def test_a_business_without_a_station_has_it_not_set_up():
    assert health() == "not_configured"
    printer("Till")
    assert health() == "not_configured"


def test_a_station_that_gave_news_in_the_last_90_seconds_is_ok():
    reaches(printer("Till"), seen=dt.timedelta(seconds=85))
    assert health() == "ok"


def test_a_station_quiet_for_more_than_90_seconds_or_that_never_gave_news_has_no_signal():
    device = reaches(printer("Till"), seen=dt.timedelta(seconds=95))
    assert health() == "no_signal"
    PrintDevice.objects.filter(pk=device.pk).update(last_seen_at=None)
    assert health() == "no_signal"
    PrintDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    assert health() == "ok"


def test_only_a_device_that_reaches_the_functions_receipt_paper_makes_its_station():
    # Another function's station on, the computer's own printer (A4 pages), a retired device or an inactive printer
    # print no receipt: none of them puts the receipts' station in green.
    reaches(printer("Kitchen", usage="kitchen", address="10.0.0.2"), name="Kitchen tablet")
    reaches(printer("Office", kind="system", address=""), name="Office")
    till = printer("Till", address="10.0.0.3")
    reaches(till, name="Old till", retired=True)
    assert (health("receipt"), health("kitchen")) == ("not_configured", "ok")

    reaches(till, name="New till")
    assert health() == "ok"
    run("printing.printer.update", {"printer_id": str(till.id), "is_active": False})
    assert health() == "not_configured"


def test_a_station_on_beside_one_quiet_is_ok():
    till = printer("Till")
    reaches(till, name="Counter", seen=dt.timedelta(minutes=10))
    reaches(till, name="Terrace", seen=dt.timedelta(seconds=10))
    assert health() == "ok"


def test_whoever_sees_the_printers_reads_it_and_nobody_else():
    assert health(ctx=ctx_for("hub_employee")) == "not_configured"
    with pytest.raises(PermissionDenied):
        run("printing.device.health", {"usage": "receipt"}, ctx=ctx_for("nobody"))
