"""The kitchen's day on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

from apps.kitchen import queries
from apps.printing.models import PrintJob

from .conftest import HUB_DB, add_line, open_check, run

pytestmark = HUB_DB

CANARY = "Atlantic/Canary"


def test_the_settings_and_the_day_are_on_the_businesss_clock(monkeypatch, in_business_a):
    monkeypatch.setattr(in_business_a, "timezone", CANARY)
    assert run("kitchen.settings.get", {}).timezone == CANARY
    # 23:30 UTC of the 2nd is the 2nd in the Canaries, the 3rd in Madrid.
    assert queries.business_day(dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC)) == dt.date(2026, 11, 2)
    assert queries.start_of(dt.date(2026, 11, 2)) == dt.datetime(2026, 11, 2, 0, 0, tzinfo=dt.UTC)


def test_a_sheet_says_when_its_round_was_sent_and_a_void_slip_when_it_was_voided(
    monkeypatch, in_business_a, clock, product, printers
):
    """The device printed its own hour (ERPlora/app#77): a copy printed a minute later said that minute, and in the
    kitchen that hour tells how long the round has been waiting. The sheet brings it, on the business's clock."""
    monkeypatch.setattr(in_business_a, "timezone", CANARY)
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    clock.advance(minutes=1)
    run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    clock.advance(minutes=5)
    run("kitchen.ticket.cancel", {"ticket_id": str(ticket.id), "reason": "Guest left"})
    # 11:00 UTC of 14 October is 12:00 in the Canaries (summer time) and 13:00 in Madrid.
    sheets = PrintJob.objects.order_by("created_at", "id")
    assert [job.document["time"] for job in sheets] == ["12:00", "12:00", "12:06"]
