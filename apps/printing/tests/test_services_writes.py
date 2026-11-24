"""The nudge a job back in the queue records (``printing.job.queued``): base's /ws/print wakes the devices with it."""

from apps.printing.tests.conftest import HUB_DB, enqueue, printer
from apps.printing.tests.test_services import claim, events, expire

pytestmark = HUB_DB


def test_a_job_back_from_an_expired_lease_wakes_the_devices():
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    expire(queued.id)
    before = len(events("printing.job.queued"))
    claim(printer("Kitchen", usage="kitchen", address="10.0.0.2"))  # reclaims the expired lease
    assert len(events("printing.job.queued")) == before + 1
    assert events("printing.job.queued")[-1]["id"] == str(queued.id)
