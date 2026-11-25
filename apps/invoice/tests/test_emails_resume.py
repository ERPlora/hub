"""The emails a stopped process left half-way (INVOICE-F26): one nobody took goes out; one already being sent is told as
not confirmed and is never sent twice on its own."""

import datetime as dt

import pytest
from django.core import mail
from django.utils import timezone
from live.context import system_context
from live.models import OutboxEvent

from apps.invoice import events
from apps.invoice.apps import InvoiceConfig
from apps.invoice.models import InvoiceEmail
from apps.invoice.tests.conftest import A, HUB_DB, run
from apps.invoice.tests.emailed import ANA, asked, emails, kept, owner
from apps.invoice.tests.manual import manual
from base.tenancy.context import current_alias

__all__ = ["owner"]

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "owner")]


@pytest.fixture
def resume(django_capture_on_commit_callbacks):
    def sweep():
        with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
            return run("invoice.email.resume", {}, system_context(A))

    return sweep


def left(status: str, minutes: int, invoice=None):
    """An email whose delivery stopped at ``status`` that many minutes ago."""
    out = asked(invoice or manual(), to=ANA)
    InvoiceEmail.objects.filter(pk=out.id).update(
        status=status, status_at=timezone.now() - dt.timedelta(minutes=minutes)
    )
    return out


def test_one_nobody_took_goes_out(resume):
    out = left("queued", 5)
    assert resume().resumed == 1
    assert (len(mail.outbox), kept(out).status) == (1, "sent")


def test_one_just_asked_for_is_left_to_its_own_delivery(resume):
    out = left("queued", 1)
    assert resume().resumed == 0
    assert (mail.outbox, kept(out).status) == ([], "queued")


def test_one_that_stopped_while_it_was_sent_is_told_as_not_confirmed_and_never_sent_twice(resume):
    invoice = manual()
    out = left("sending", 11, invoice)
    assert resume().unconfirmed == 1
    assert (mail.outbox, kept(out).status, kept(out).error_code) == ([], "failed", "invoice.email_unconfirmed")
    [row] = emails(invoice).emails
    assert row.reason and row.sent_at is None
    assert OutboxEvent.objects.filter(name=events.EMAIL_FAILED).count() == 1
    assert resume().unconfirmed == 0


def test_one_still_being_sent_is_left_alone(resume):
    out = left("sending", 5)
    assert resume().unconfirmed == 0
    assert kept(out).status == "sending"


@pytest.mark.parametrize("status", ["sent", "failed"])
def test_what_already_ended_is_never_touched(resume, status):
    out = left(status, 60)
    resume()
    assert (mail.outbox, kept(out).status) == ([], status)


def test_the_worker_looks_for_them_every_five_minutes():
    [task] = [task for task in InvoiceConfig.scheduled_tasks if task["operation"] == "invoice.email.resume"]
    assert (task["cron"], task["catch_up"]) == ("*/5 * * * *", "collapse")
