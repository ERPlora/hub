"""Emailing an invoice (INVOICE-F26). The request is kept in a short transaction; its PDF is printed and the mail server is
asked after the COMMIT, in a thread of the process's own (``base.outbound``), with no transaction and no lock; how it
ended is kept in another short one. A mail server takes no key of ours, so one it may have taken is never sent again on
its own."""

import datetime as dt
from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import get, operation
from live.outbox import record_event

from apps.invoice import events
from apps.invoice.models import Invoice, InvoiceEmail
from apps.invoice.queries.emails import NO_REPLY, REASONS, UNAVAILABLE, email_row, message_of, proposed_address
from apps.invoice.queries.rows import find_invoice
from apps.invoice.schemas.emails import (
    EmailClaimOut,
    EmailRecordIn,
    EmailRecordOut,
    EmailRefIn,
    EmailResumeIn,
    EmailResumeOut,
    InvoiceEmailOut,
    SendEmailIn,
)
from apps.invoice.services.writes import _now, actor
from base import business_mail, outbound
from base.operations import is_demo_hub

#: Only the system context (``*``) holds it: no role declares it.
DELIVER = "invoice.deliver_email"
#: How long one may wait for its delivery before the worker hands it over again.
QUEUED_AT_MOST = dt.timedelta(minutes=2)
#: How long one may be on its way before it is told as not confirmed; past what printing and the mail server take.
SENDING_AT_MOST = dt.timedelta(minutes=10)
#: How many one pass of the worker takes per business.
RESUME_BATCH = 50

ADDRESS_MISSING = _("Enter the email to send it to.")
DEMO = _("A demo does not send emails.")
KEY_REUSED = _("That request key already belongs to another email.")


def _refuse_unless_it_may_send(ctx: OperationContext) -> None:
    with translation.override(ctx.language):
        if is_demo_hub(ctx.scope):
            raise Conflict(str(DEMO), code="invoice.email_demo")
        if not business_mail.reply_address(ctx.scope):
            raise Conflict(str(REASONS[NO_REPLY]), code=NO_REPLY)


def _address(ctx: OperationContext, data: SendEmailIn, invoice: Invoice) -> str:
    to = data.to or proposed_address(invoice)
    if not to:
        with translation.override(ctx.language):
            raise InvalidPayload(str(ADDRESS_MISSING), fields={"to": str(ADDRESS_MISSING)})
    return to


def _said(ctx: OperationContext, email: InvoiceEmail) -> dict:
    with translation.override(ctx.language):
        return email_row(email)


def _tell(ctx: OperationContext, name: str, email: InvoiceEmail) -> None:
    record_event(
        ctx, name, {"id": str(email.id), "invoice_id": str(email.invoice_id), "number": email.invoice.number}
    )


@operation(
    "invoice.email.send",
    kind="command",
    permission="invoice.add_invoice",
    input=SendEmailIn,
    output=InvoiceEmailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "email Carpintería Lema theirs",
                "drop it into Carpintería Lema's inbox",
            ),
            "es": (
                "mándale la suya por correo a Carpintería Lema",
                "envíasela por correo a Nuria, a nuria@example.com",
            ),
        },
        "description": "Emails one invoice, with its PDF, to its customer: to the address given, or else to the one on "
        "their card; their replies go to the owner of the business. It leaves in a moment, really and once per call: "
        "invoice.email.list says whether it left. The invoice does not change.",
        # What leaves cannot be called back, and no automation sends it alone.
        "risk": "high",
        "preview": {"operation": "invoice.email.list", "fields": ["customer_email"]},
    },
)
def send_email(ctx: OperationContext, data: SendEmailIn) -> dict:
    invoice = find_invoice(ctx, data.invoice_id, data.number)
    _refuse_unless_it_may_send(ctx)
    wanted = {"to_address": _address(ctx, data, invoice), "requested_by": actor(ctx), "invoice": invoice}
    if data.attempt_key is None:
        email, created = InvoiceEmail.objects.create(**wanted), True
    else:
        email, created = InvoiceEmail.objects.get_or_create(attempt_key=data.attempt_key, defaults=wanted)
    if not created:
        if email.invoice_id != invoice.id:
            with translation.override(ctx.language):
                raise Conflict(str(KEY_REUSED), code="invoice.email_key_reused")
        return _said(ctx, email)
    _tell(ctx, events.EMAIL_REQUESTED, email)
    outbound.after_commit(deliver, ctx.scope, email.id)
    return _said(ctx, email)


# ── The delivery, outside any transaction ───────────────────────────────────────────────────────


def deliver(scope: Scope, email_id: UUID) -> None:
    """Print the PDF of an email nobody took yet and hand it to the mail server; how it ended is always kept."""
    system = system_context(scope)
    claimed = get("invoice.email.claim")(system, EmailRefIn(id=email_id))
    if not claimed.claimed:
        return
    failure = UNAVAILABLE
    try:
        failure = _handed_over(system, email_id, claimed)
    finally:
        get("invoice.email.record")(system, EmailRecordIn(id=email_id, failure=failure))


def _handed_over(ctx: OperationContext, email_id: UUID, claimed: EmailClaimOut) -> str:
    """Empty once the mail server took it; else why not."""
    reply_to = business_mail.reply_address(ctx.scope)
    if not reply_to:
        return NO_REPLY
    try:
        message = message_of(ctx, claimed.invoice_id)
    except OperationError as refused:
        return refused.code
    letter = business_mail.Letter(
        to=claimed.to,
        reply_to=reply_to,
        subject=message.subject,
        body=message.body,
        key=email_id,
        filename=message.filename,
        content=message.content,
        content_type=message.content_type,
    )
    outbound.release()  # the mail server is waited for with no connection held
    try:
        business_mail.send(letter)
    except business_mail.NotSent as failure:
        return f"invoice.email_{failure.code}"
    return ""


@operation(
    "invoice.email.claim",
    kind="command",
    permission=DELIVER,
    input=EmailRefIn,
    output=EmailClaimOut,
    ai={
        "description": "System only: takes an email that waits to leave, so that nobody else sends it.",
        "risk": "normal",
    },
)
def claim_email(ctx: OperationContext, data: EmailRefIn) -> dict:
    email = (
        InvoiceEmail.objects.select_for_update(skip_locked=True)
        .filter(pk=data.id, status=InvoiceEmail.Status.QUEUED)
        .first()
    )
    if email is None:
        return {"claimed": False}
    email.status, email.status_at = InvoiceEmail.Status.SENDING, _now()
    email.save(update_fields=["status", "status_at"])
    return {"claimed": True, "invoice_id": email.invoice_id, "to": email.to_address}


@operation(
    "invoice.email.record",
    kind="command",
    permission=DELIVER,
    input=EmailRecordIn,
    output=EmailRecordOut,
    ai={
        "description": "System only: keeps how an email ended, sent or why not.",
        "risk": "normal",
    },
)
def record_email(ctx: OperationContext, data: EmailRecordIn) -> dict:
    email = (
        InvoiceEmail.objects.select_for_update(of=("self",))
        .select_related("invoice")
        .filter(pk=data.id, status=InvoiceEmail.Status.SENDING)
        .first()
    )
    if email is None:
        return {"status": None}
    _end(ctx, email, data.failure)
    return {"status": email.status}


def _end(ctx: OperationContext, email: InvoiceEmail, failure: str) -> None:
    now = _now()
    email.status = InvoiceEmail.Status.FAILED if failure else InvoiceEmail.Status.SENT
    email.status_at, email.error_code = now, failure
    email.sent_at = None if failure else now
    email.save(update_fields=["status", "status_at", "error_code", "sent_at"])
    _tell(ctx, events.EMAIL_FAILED if failure else events.EMAIL_SENT, email)


@operation(
    "invoice.email.resume",
    kind="command",
    permission=DELIVER,
    input=EmailResumeIn,
    output=EmailResumeOut,
    ai={
        "description": "System only (the worker's scheduled task): hands over again the emails nobody took, and tells as "
        "not confirmed the ones that stopped while they were sent.",
        "risk": "normal",
    },
)
def resume_emails(ctx: OperationContext, data: EmailResumeIn) -> dict:
    now = _now()
    waiting = InvoiceEmail.objects.select_for_update(of=("self",), skip_locked=True).order_by("status_at", "id")
    lost = waiting.filter(status=InvoiceEmail.Status.QUEUED, status_at__lt=now - QUEUED_AT_MOST)
    lost = list(lost.values_list("id", flat=True)[:RESUME_BATCH])
    stopped = waiting.filter(status=InvoiceEmail.Status.SENDING, status_at__lt=now - SENDING_AT_MOST)
    stopped = list(stopped.select_related("invoice")[:RESUME_BATCH])
    for email_id in lost:
        outbound.after_commit(deliver, ctx.scope, email_id)
    for email in stopped:
        _end(ctx, email, "invoice.email_unconfirmed")
    return {"resumed": len(lost), "unconfirmed": len(stopped)}
