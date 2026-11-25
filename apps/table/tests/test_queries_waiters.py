"""The waiters of the room (``table.waiter.list``): who opened its checks, once each, by name."""

import pytest
from django.utils import timezone

from .conftest import HUB_DB, make_session, make_table, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_the_waiters_are_who_opened_checks_once_each_by_name():
    make_session(make_table("1"), waiter_id="2", waiter_name="Luis")
    make_session(make_table("2"), waiter_id="1", waiter_name="Ana")
    make_session(
        make_table("3"),
        waiter_id="1",
        waiter_name="Ana",
        status="closed",
        closed_at=timezone.now(),
    )
    rows = run("table.waiter.list", {}).rows
    assert [(r.id, r.name) for r in rows] == [("1", "Ana"), ("2", "Luis")]
