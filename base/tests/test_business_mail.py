"""The mail a business sends its customers: ERPlora's sender, the replies to the owner, and a failure that is told."""

import logging
import smtplib
import uuid

import pytest
from botocore.exceptions import ClientError
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend

from base import business_mail
from base.models import Hub, Membership
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

KEY = uuid.UUID("01a16000-0000-7000-8000-0000000000ff")


def letter(**more) -> business_mail.Letter:
    return business_mail.Letter(
        **{
            "to": "ana@example.com",
            "reply_to": "olga@example.com",
            "subject": "Invoice FACT-2026-000001",
            "body": "Hello",
            "key": KEY,
            "filename": "FACT-2026-000001.pdf",
            "content": b"%PDF-1.7 x",
            "content_type": "application/pdf",
            **more,
        }
    )


def photo(*members: dict) -> None:
    Hub.objects.filter(slug=A.key).update(state={"members": list(members)})


def member(user_id: str, role: str, email: str) -> dict:
    return {"user_id": user_id, "role": role, "email": email, "name": user_id}


def failing(monkeypatch, failure) -> None:
    def send(self, messages):
        raise failure

    monkeypatch.setattr(EmailBackend, "send_messages", send)


# Where its replies go


def test_the_replies_go_to_the_owner_of_the_business():
    photo(member("2", "hub_admin", "adam@example.com"), member("1", "hub_owner", "olga@example.com"))
    assert business_mail.reply_address(A) == "olga@example.com"


def test_the_owner_who_already_entered_is_read_from_their_account(django_user_model):
    user = django_user_model.objects.create_user(username="saas:1", email="olga@bar.example")
    Membership.objects.create(user=user, host=A.key, role=Membership.Role.OWNER)
    assert business_mail.reply_address(A) == "olga@bar.example"


def test_a_business_whose_owner_has_no_email_has_nowhere_to_reply():
    photo(member("1", "hub_owner", ""), member("2", "hub_admin", "adam@example.com"))
    assert business_mail.reply_address(A) == ""


def test_another_business_owner_is_never_taken():
    photo(member("1", "hub_owner", "olga@example.com"))
    assert business_mail.reply_address(B) == ""


# What leaves


def test_it_leaves_as_the_platform_with_the_replies_to_the_business_and_its_file(settings):
    settings.DEFAULT_FROM_EMAIL = "ERPlora <noreply@erplora.com>"
    business_mail.send(letter())
    [sent] = mail.outbox
    assert (sent.from_email, sent.to, sent.reply_to) == (
        "ERPlora <noreply@erplora.com>",
        ["ana@example.com"],
        ["olga@example.com"],
    )
    assert (sent.subject, sent.body, sent.cc, sent.bcc) == ("Invoice FACT-2026-000001", "Hello", [], [])
    [attached] = sent.attachments
    assert tuple(attached) == ("FACT-2026-000001.pdf", b"%PDF-1.7 x", "application/pdf")


def test_the_same_letter_always_carries_the_same_id_so_a_mailbox_shows_it_once(settings):
    settings.DEFAULT_FROM_EMAIL = "ERPlora <noreply@erplora.com>"
    business_mail.send(letter())
    business_mail.send(letter())
    assert [sent.message()["Message-ID"] for sent in mail.outbox] == [f"<{KEY}@erplora.com>"] * 2


def test_a_name_with_a_line_break_stays_one_subject():
    business_mail.send(letter(subject="Invoice 1 from Bar\nBcc: all@example.com"))
    [sent] = mail.outbox
    assert sent.subject == "Invoice 1 from Bar Bcc: all@example.com"
    assert sent.message()["Bcc"] is None


# What does not leave is told


def test_an_address_the_server_refuses_for_good_is_told_as_such(monkeypatch):
    failing(monkeypatch, smtplib.SMTPRecipientsRefused({"ana@example.com": (550, b"No such user")}))
    with pytest.raises(business_mail.NotSent) as failure:
        business_mail.send(letter())
    assert failure.value.code == business_mail.REFUSED


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPRecipientsRefused({"ana@example.com": (450, b"Try later")}),
        smtplib.SMTPAuthenticationError(535, b"no"),
        smtplib.SMTPServerDisconnected("gone"),
        ConnectionRefusedError("no server"),
        TimeoutError("slow"),
        ClientError({"Error": {"Code": "AccessDenied", "Message": "sandbox"}}, "SendRawEmail"),
    ],
    ids=lambda failure: type(failure).__name__,
)
def test_a_server_that_cannot_take_it_now_is_told_as_such(monkeypatch, caplog, failure):
    failing(monkeypatch, failure)
    with caplog.at_level(logging.WARNING), pytest.raises(business_mail.NotSent) as told:
        business_mail.send(letter())
    assert told.value.code == business_mail.UNAVAILABLE
    assert type(failure).__name__ in caplog.text
    assert "ana@example.com" not in caplog.text


def test_a_backend_that_takes_nothing_did_not_send_it(monkeypatch):
    monkeypatch.setattr(EmailBackend, "send_messages", lambda self, messages: 0)
    with pytest.raises(business_mail.NotSent) as told:
        business_mail.send(letter())
    assert told.value.code == business_mail.UNAVAILABLE
