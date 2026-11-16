"""The test page on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

from django.utils import timezone

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import HUB_DB, printer, run

pytestmark = HUB_DB


def test_the_a4_test_page_is_printed_at_the_businesss_hour(monkeypatch, in_business_a):
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC))
    monkeypatch.setattr(in_business_a, "timezone", "Atlantic/Canary")
    printer("Office", kind="system", address="")
    out = run("printing.printer.test", {"printer": "Office"})
    html = PrintJob.objects.get(pk=out.id).html
    assert "Nov. 2, 2026, 9 a.m." in html
