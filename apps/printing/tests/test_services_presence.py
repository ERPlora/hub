"""``printing.device.seen`` with more than one device set up in the business: only the device that says it is there
is seen, so the bell keeps ringing for the jobs that only a silent device prints."""

import datetime as dt

from django.utils import timezone

from apps.printing.models import PrintDevice, PrintJob
from apps.printing.tests.conftest import HUB_DB, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import EMPLOYEE, ITEM, TILL_ID, register, seen_at

pytestmark = HUB_DB

KITCHEN_ID = "c41e8a07-2d93-4b5f-a6e8-71f0b3d9c254"


def gave_news(device_id: str, minutes: int) -> dt.datetime:
    """The device ``device_id`` last gave news ``minutes`` ago; that instant."""
    instant = timezone.now() - dt.timedelta(minutes=minutes)
    PrintDevice.objects.filter(key=PrintDevice.key_of(device_id)).update(last_seen_at=instant)
    return instant


def bell(usage: str) -> int:
    return run("printing.device.coverage", {"usage": usage}).count


def test_a_device_that_says_it_is_there_marks_only_itself_and_the_bell_still_rings_for_the_other():
    register(printer("Till"), device=TILL_ID, name="Counter till")
    register(printer("Kitchen", usage="kitchen", address="10.0.0.2"), device=KITCHEN_ID, name="Kitchen tablet")
    gave_news(TILL_ID, minutes=10)
    kitchen_quiet = gave_news(KITCHEN_ID, minutes=20)
    enqueue()
    enqueue("kitchen_order", {"order_number": "M-12", "items": [ITEM]})
    PrintJob.objects.update(created_at=timezone.now() - dt.timedelta(seconds=65))
    assert (bell("receipt"), bell("kitchen")) == (1, 1), "both devices are off"

    before = timezone.now()
    assert run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE)).seen is True

    assert before <= seen_at(TILL_ID) <= timezone.now()
    assert seen_at(KITCHEN_ID) == kitchen_quiet, "the kitchen tablet said nothing"
    assert (bell("receipt"), bell("kitchen")) == (0, 1), "nobody is printing the kitchen order"
