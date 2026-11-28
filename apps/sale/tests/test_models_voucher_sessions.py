"""The voucher sessions done outside the till: one row per session of Services."""

import datetime as dt
from uuid import uuid7

from apps.sale.models.voucher_sessions import VoucherSession
from apps.sale.tests.conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_a_session_done_outside_the_till_counts_once_for_who_did_it():
    session, staff, day = uuid7(), uuid7(), dt.date(2026, 10, 14)
    done = VoucherSession.objects.create(session_id=session, staff_id=staff, business_day=day, value=1200)
    assert str(done) == f"{staff}: 1200"
    refused(lambda: VoucherSession.objects.create(session_id=session, staff_id=uuid7(), business_day=day, value=900))
