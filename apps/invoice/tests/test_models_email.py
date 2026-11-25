"""The log of the emails of an invoice: what the database keeps and refuses."""

import uuid

import pytest
from django.db import IntegrityError
from live.operations import atomic

from apps.invoice.models import InvoiceEmail
from apps.invoice.tests.conftest import HUB_DB
from apps.invoice.tests.manual import manual, stored

pytestmark = HUB_DB


def logged(invoice, **more) -> InvoiceEmail:
    return InvoiceEmail.objects.create(invoice=invoice, to_address="ana@example.com", **more)


def test_an_email_waits_to_leave_until_it_is_sent(issuer):
    email = logged(stored(manual()))
    assert (email.status, email.sent_at, email.error_code) == (InvoiceEmail.Status.QUEUED, None, "")
    assert email.id.version == 7
    assert email.requested_at is not None and email.status_at is not None


def test_one_request_is_one_email_and_those_without_a_key_are_never_the_same(issuer):
    invoice = stored(manual())
    key = uuid.uuid4()
    logged(invoice, attempt_key=key)
    with pytest.raises(IntegrityError), atomic():
        logged(invoice, attempt_key=key)
    logged(invoice)
    logged(invoice)
    assert invoice.emails.count() == 3


def test_the_newest_comes_first(issuer):
    invoice = stored(manual())
    first, second = logged(invoice), logged(invoice)
    assert list(invoice.emails.all()) == [second, first]


def test_its_name_says_no_address(issuer):
    assert "ana@example.com" not in str(logged(stored(manual())))
