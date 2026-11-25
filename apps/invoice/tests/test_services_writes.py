"""What the invoice's writes log goes under one logger, ``apps.invoice.services``, whichever of its modules it
happens in."""

import dataclasses
import logging

import pytest
from live.errors import Conflict

from apps.invoice.tests.conftest import HUB_DB, ctx_for, run

pytestmark = HUB_DB

LINE = {"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}


def test_what_the_writes_log_goes_under_the_invoice_writes(issuer, customer, caplog):
    # A ticket for a card whose name is longer than VeriFactu's 120 characters goes without the name, and Printing
    # refuses the page of a caller without the permission to print.
    card = customer("x" * 150)
    admin = ctx_for()
    cannot_print = dataclasses.replace(admin, permissions=admin.permissions - {"printing.print"})
    with caplog.at_level(logging.WARNING):
        ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE], "customer_id": str(card.id)})
        with pytest.raises(Conflict):
            run("invoice.invoice.print", {"invoice_id": str(ticket.id)}, cannot_print)
    said = sorted((record.msg, record.name) for record in caplog.records if record.msg.startswith("invoice: "))
    assert said == [
        ("invoice: Printing did not queue %s (%s)", "apps.invoice.services"),
        ("invoice: a ticket goes without its recipient's name (%s)", "apps.invoice.services"),
    ]
