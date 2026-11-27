"""An order sent while the table's QR is being regenerated: real sessions in threads, real row locks.

The send holds the row of the table's code until it commits, so a regeneration that has already changed the code makes
the send wait, and the old code then opens nothing: no order is ever saved for a QR that no longer works.
"""

import pytest

from apps.customer.tests.conftest import writes
from apps.online_order.models import Order, TableCode
from base.tenancy.tests.concurrency import meanwhile, plan_with_room

from .conftest import HUB_DB_COMMITTED, make_table, regenerate, run, visitor

__all__ = ["plan_with_room"]

pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room", "spa_manifest")]


def test_an_order_sent_while_its_qr_is_regenerated_waits_and_writes_nothing(dishes):
    table = make_table("4")
    old = regenerate(table)

    def send_with_the_old_code():
        line = {"product_id": str(dishes["cola"].id)}
        return run("online_order.public.send", {"code": old, "lines": [line]}, visitor())

    with meanwhile(writes("online_order_tablecode"), send_with_the_old_code) as sent:
        regenerate(table)
    assert getattr(sent[0], "code", sent[0]) == "online_order.qr_not_active"
    assert (Order.objects.count(), TableCode.objects.filter(code=old).exists()) == (0, False)
