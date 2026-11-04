"""The test page on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

import pytest
from django.utils import timezone

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import printer, run
from base.models import Hub
from base.tenancy.context import use_hub

pytestmark = pytest.mark.django_db


def test_the_a4_test_page_is_printed_at_the_businesss_hour(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC))
    printer("Office", kind="system", address="")
    with use_hub(Hub(slug="a", timezone="Atlantic/Canary")):
        out = run("printing.printer.test", {"printer": "Office"})
    html = PrintJob.objects.get(pk=out.id).html
    assert "Nov. 2, 2026, 9 a.m." in html
