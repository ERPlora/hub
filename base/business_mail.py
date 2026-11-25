"""The mail a business sends its customers: it leaves as ERPlora, and its replies go to the business.

The mail server sends only as ERPlora's mailbox, which discards what it receives, so every letter says where its replies
go: the email of the account of the business's owner, the one address of a business the Hub knows.
"""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.utils import parseaddr

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import EmailMessage
from live.context import Scope

from base.models import Membership
from base.queries.people import people_of

logger = logging.getLogger(__name__)

#: The address takes no mail: sending it again changes nothing.
REFUSED = "refused"
#: The mail server could not take it now.
UNAVAILABLE = "unavailable"
#: From this reply code on, a mail server refuses for good (RFC 5321, 4.2.1).
PERMANENT = 500


class NotSent(Exception):
    """The letter did not leave; ``code`` says why (``REFUSED``, ``UNAVAILABLE``)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Letter:
    """One email to one customer, with one file."""

    to: str
    reply_to: str
    subject: str
    body: str
    #: Names the letter: a mailbox that gets it twice shows it once.
    key: uuid.UUID
    filename: str
    content: bytes
    content_type: str


def reply_address(scope: Scope) -> str:
    """Where the replies to ``scope``'s business go; empty when no owner of it has an email."""
    owners = (person for person in people_of(scope.key) if person["role"] == Membership.Role.OWNER)
    return next((person["email"] for person in owners if person["email"]), "")


def send(letter: Letter) -> None:
    """Hand ``letter`` to the mail server, or ``NotSent``: whoever calls it has no transaction open."""
    message = EmailMessage(
        subject=" ".join(letter.subject.split()),
        body=letter.body,
        to=[letter.to],
        reply_to=[letter.reply_to],
        attachments=[(letter.filename, letter.content, letter.content_type)],
        headers={"Message-ID": f"<{letter.key}@{_sender_domain()}>"},
    )
    try:
        taken = message.send()
    except (smtplib.SMTPException, OSError, BotoCoreError, ClientError) as failure:
        # Its text may carry the customer's address: only its kind is logged.
        logger.warning("business mail: %s did not leave (%s)", letter.key, type(failure).__name__)
        raise NotSent(_why(failure)) from failure
    if not taken:
        raise NotSent(UNAVAILABLE)


def _why(failure: Exception) -> str:
    if isinstance(failure, smtplib.SMTPRecipientsRefused):
        answers = [code for code, _text in failure.recipients.values()]
        if answers and min(answers) >= PERMANENT:
            return REFUSED
    return UNAVAILABLE


def _sender_domain() -> str:
    return parseaddr(settings.DEFAULT_FROM_EMAIL)[1].partition("@")[2]
