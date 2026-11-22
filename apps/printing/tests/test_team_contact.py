"""Who asked for a print job or cancelled it never shows a colleague's email (BASE-F119, PRINTING-F01, PRINTING-F14).

A colleague whose account has no name of its own is named by the part before the «@» in the print queue, and that is
what is kept: an employee who sees no colleague's contact details reads it there. What was saved with an address
before is cleaned once by the app's migration (``test_migrations``).
"""

import pytest

from apps.flow.tests.test_api import get, post
from apps.printing.models import PrintJob
from base.tests.colleagues import ADDRESS, NAMELESS, SHOWN, signed_in

from .conftest import HUB_DB, printer

pytestmark = HUB_DB


@pytest.mark.parametrize("account", NAMELESS.values(), ids=NAMELESS)
def test_a_colleague_without_a_name_who_prints_or_cancels_is_named_without_their_address(account):
    printer("Till")
    zoe = signed_in("zoe", "hub_admin", **account)
    tested = post(zoe, "/printing/printers/test", {"printer": "Till"})
    assert tested.status_code == 201, tested.content
    job = tested.json()["id"]
    assert post(zoe, "/printing/jobs/cancel", {"job_id": job, "reason": "Out of paper"}).status_code == 200

    queue = get(signed_in("ana"), "/printing/jobs")

    assert queue.status_code == 200, queue.content
    assert ADDRESS not in queue.content.decode()
    assert [(row["created_by"], row["cancelled_by"]) for row in queue.json()["rows"]] == [(SHOWN, SHOWN)]
    saved = PrintJob.objects.get(pk=job)
    assert (saved.created_by, saved.cancelled_by) == (SHOWN, SHOWN)
