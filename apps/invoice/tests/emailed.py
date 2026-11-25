"""An invoice emailed to its customer, for the tests that need one: asked for, delivered as the Hub delivers it after the
COMMIT, or left to a mail server that fails."""

import smtplib
import uuid

import pytest
from django.core.mail.backends.locmem import EmailBackend

from apps.invoice.models import InvoiceEmail
from apps.invoice.tests.conftest import A, run
from base.models import Hub
from base.tenancy.context import current_alias

SEND = "invoice.email.send"
LIST = "invoice.email.list"
OWNER = "olga@example.com"
ANA = "ana@example.com"


def owned(email: str = OWNER, scope=A) -> None:
    """The business of ``scope`` belongs to the account of ``email``, as erplora.com's photo says."""
    Hub.objects.filter(slug=scope.key).update(
        state={"members": [{"user_id": "1", "role": "hub_owner", "email": email, "name": "Olga"}]}
    )


@pytest.fixture
def owner(in_business_a):
    owned()


@pytest.fixture
def send(django_capture_on_commit_callbacks):
    """``send(answer, ctx, **more)``: the email of that invoice, asked for and, after the COMMIT, delivered."""

    def ask(answer, ctx=None, **more):
        with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
            return run(SEND, {"invoice_id": str(answer.id), **more}, ctx)

    return ask


def asked(answer, ctx=None, **more):
    """Asked for, with its COMMIT still to come."""
    return run(SEND, {"invoice_id": str(answer.id), **more}, ctx)


def emails(answer, ctx=None):
    """What the invoice's screen reads of its emails."""
    return run(LIST, {"invoice_id": str(answer.id)}, ctx)


def kept(out) -> InvoiceEmail:
    return InvoiceEmail.objects.get(pk=out.id)


def key() -> str:
    return str(uuid.uuid4())


def mail_server_fails(monkeypatch, failure: Exception | None = None) -> None:
    def refuse(self, messages):
        raise failure or smtplib.SMTPServerDisconnected("gone")

    monkeypatch.setattr(EmailBackend, "send_messages", refuse)
