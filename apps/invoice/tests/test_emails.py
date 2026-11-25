"""Emailing an invoice (INVOICE-F26): asked for in a transaction, printed and handed to the mail server after its COMMIT,
and told as it ended. Nothing of the invoice changes."""

import base64
import dataclasses
import smtplib
from types import SimpleNamespace

import pytest
from django.core import mail
from django.utils import translation
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import atomic, get
from pydantic import ValidationError

from apps.customer.models import Customer
from apps.invoice import events
from apps.invoice.models import Invoice, InvoiceEmail
from apps.invoice.queries import pdf as pdf_query
from apps.invoice.queries.emails import REASONS, reason_of
from apps.invoice.queries.pdf import file_name
from apps.invoice.services import emails as service
from apps.invoice.tests.conftest import A, B, HUB_DB, ctx_for, fields, run
from apps.invoice.tests.emailed import ANA, OWNER, SEND, asked, emails, kept, key, mail_server_fails, owned, owner, send
from apps.invoice.tests.manual import NOON, RECIPIENT, manual, stored, withheld
from apps.invoice.tests.printed import text, words
from apps.verifactu.models import Record
from base import outbound, pdf
from base.models import Hub
from base.tenancy.context import current_alias, use_hub

__all__ = ["owner", "send"]

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "owner")]


class Attached:
    """The file of a mail, as ``printed``'s helpers open an answer of the server."""

    def __init__(self, message):
        [attachment] = message.attachments
        self.name, self.content, self.kind = tuple(attachment)

    def words(self):
        return words(text(SimpleNamespace(content_base64=base64.b64encode(self.content).decode())))


def only_mail():
    [message] = mail.outbox
    return message


def events_of(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")]


def business(**values) -> None:
    Hub.objects.filter(slug=A.key).update(**values)


# What leaves


def test_the_customer_gets_the_invoice_with_its_pdf_and_replies_to_the_business(send, settings):
    settings.DEFAULT_FROM_EMAIL = "ERPlora <noreply@erplora.com>"
    invoice = manual(notes="Pay by transfer")
    out = send(invoice, to=ANA)
    message = only_mail()
    assert (message.from_email, message.to, message.reply_to) == ("ERPlora <noreply@erplora.com>", [ANA], [OWNER])
    attached = Attached(message)
    assert (attached.name, attached.kind) == (file_name(stored(invoice)), "application/pdf")
    downloaded = run("invoice.invoice.pdf", {"invoice_id": str(invoice.id)})
    assert attached.words() == words(text(downloaded))
    assert (kept(out).status, kept(out).to_address, kept(out).requested_by) == ("sent", ANA, "tester")


def test_nothing_is_printed_nor_sent_until_the_request_is_committed(monkeypatch):
    monkeypatch.setattr(pdf, "render_pdf", lambda html: pytest.fail("printed inside the transaction"))
    out = asked(manual(), to=ANA)
    assert (out.status, mail.outbox) == ("queued", [])


def test_a_request_that_rolls_back_sends_nothing(django_capture_on_commit_callbacks):
    invoice = manual()
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()) as left:
        with pytest.raises(RuntimeError), atomic():
            asked(invoice, to=ANA)
            raise RuntimeError
    assert (left, mail.outbox, InvoiceEmail.objects.count()) == ([], [], 0)


def test_by_default_it_goes_to_the_email_of_the_customers_card(customer, send):
    card = customer("Ana López", email=ANA, tax_id="12345678Z", address="Calle Luna 3")
    invoice = manual(customer_id=str(card.id))
    assert emails(invoice).customer_email == ANA
    send(invoice)
    assert only_mail().to == [ANA]


def test_a_typed_address_wins_and_never_changes_the_card(customer, send):
    card = customer("Ana López", email=ANA)
    invoice = manual(customer_id=str(card.id))
    send(invoice, to="facturas@example.com")
    assert only_mail().to == ["facturas@example.com"]
    assert Customer.objects.get(pk=card.id).email == ANA


def test_the_email_of_a_deleted_card_is_not_proposed(customer):
    card = customer("Ana López", email=ANA)
    invoice = manual(customer_id=str(card.id))
    run("customer.customer.delete", {"id": str(card.id)})
    assert emails(invoice).customer_email == ""


@pytest.mark.parametrize("to", [None, "", "   "])
def test_without_an_address_anywhere_it_asks_for_one(to):
    invoice = manual()
    with pytest.raises(InvalidPayload) as refused:
        asked(invoice, to=to)
    assert set(refused.value.fields) == {"to"}
    assert InvoiceEmail.objects.count() == 0


@pytest.mark.parametrize("to", ["ana", "ana@", "ana@example.com, luis@example.com", "a@b.es\nBcc: x@y.es"])
def test_what_is_no_address_is_refused_in_its_field(to):
    with pytest.raises(ValidationError) as refused:
        asked(manual(), to=to)
    assert fields(refused.value) == {"to"}


def test_it_is_sent_again_as_often_as_asked_each_one_kept(send):
    invoice = manual()
    send(invoice, to=ANA)
    send(invoice, to="luis@example.com")
    assert [message.to for message in mail.outbox] == [[ANA], ["luis@example.com"]]
    assert [(row.to, row.status) for row in emails(invoice).emails] == [("luis@example.com", "sent"), (ANA, "sent")]


def test_the_same_request_twice_sends_once(send):
    invoice, attempt = manual(), key()
    first = send(invoice, to=ANA, attempt_key=attempt)
    second = send(invoice, to=ANA, attempt_key=attempt)
    assert (second.id, len(mail.outbox), InvoiceEmail.objects.count()) == (first.id, 1, 1)


def test_a_key_is_of_one_request_only(send):
    attempt = key()
    send(manual(), to=ANA, attempt_key=attempt)
    with pytest.raises(Conflict) as refused:
        asked(manual(), to=ANA, attempt_key=attempt)
    assert refused.value.code == "invoice.email_key_reused"


# What it says


def test_it_is_written_in_the_language_of_the_business_whoever_sends_it(send):
    business(language="es", name="Bar Manolo")
    invoice = manual()
    send(invoice, ctx_for(language="en"), to=ANA)
    message = only_mail()
    assert message.subject == f"Factura {invoice.number} de Bar Manolo"
    assert "Hola, Talleres Pérez SL:" in message.body
    assert "Total: 12,10" in message.body
    assert Attached(message).words()["factura"] > 0


def test_an_invoice_with_a_language_of_its_own_is_sent_in_it(send):
    business(language="es")
    invoice = manual()
    Invoice.objects.filter(pk=invoice.id).update(language="en")
    send(invoice, to=ANA)
    assert only_mail().subject.startswith(f"Invoice {invoice.number} from ")
    assert Attached(only_mail()).words()["invoice"] > 0


def test_what_the_customer_pays_is_the_total_without_what_they_withhold(send):
    business(language="es")
    send(withheld(15), to=ANA)
    assert "Total a pagar: 106,00" in only_mail().body
    assert "121,00" not in only_mail().body


def test_it_says_when_it_is_due(at, send):
    at(NOON)
    business(language="es")
    send(manual(due_date="2026-12-10"), to=ANA)
    assert "Fecha: 24/11/2026" in only_mail().body
    assert "Vencimiento: 10/12/2026" in only_mail().body


def test_without_a_due_date_it_says_none(send):
    send(manual(), to=ANA)
    assert "Due date" not in only_mail().body


def test_a_ticket_names_no_customer(charge, product, send):
    product()
    sale = charge("mail-ticket")
    ticket = run("invoice.invoice.by_source", {"sale_id": str(sale.id)}).invoice
    send(ticket, to=ANA)
    assert only_mail().body.startswith("Hello:")
    assert only_mail().subject.startswith(f"Simplified invoice {ticket.number}")


def test_a_rectifying_invoice_says_so_and_its_amount_is_negative(send):
    invoice = manual()
    rectification = run("invoice.invoice.rectify", {"invoice_id": str(invoice.id), "reason": "Error"}).invoice
    send(rectification, to=ANA)
    assert only_mail().subject.startswith(f"Rectifying invoice {rectification.number}")
    assert "-€12.10" in only_mail().body


def test_names_are_written_as_they_are_never_as_html(send):
    business(name="Bar & Café <Sol>")
    send(manual(customer_name="Ana & Hijos"), to=ANA)
    assert "Bar & Café <Sol>" in only_mail().body
    assert "Ana & Hijos" in only_mail().body


def test_the_document_of_a_sale_goes_as_a_copy_as_its_download(charge, product, send):
    product()
    sale = charge("mail-copy", document_type="invoice", **RECIPIENT)
    invoice = run("invoice.invoice.by_source", {"sale_id": str(sale.id)}).invoice
    send(invoice, to=ANA)
    assert Attached(only_mail()).words()["copy"] == 1


def test_an_invoice_made_by_hand_goes_as_the_original(send):
    send(manual(), to=ANA)
    assert Attached(only_mail()).words()["copy"] == 0


# Nothing of the invoice changes


def test_the_invoice_and_its_verifactu_record_stay_as_they_were(send):
    invoice = manual()
    before = Invoice.objects.filter(pk=invoice.id).values().get()
    records = list(Record.objects.order_by("pk").values())
    issued = len(events_of(events.INVOICE_ISSUED))
    send(invoice, to=ANA)
    assert Invoice.objects.filter(pk=invoice.id).values().get() == before
    assert list(Record.objects.order_by("pk").values()) == records
    assert len(events_of(events.INVOICE_ISSUED)) == issued


# Who sends


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
def test_whoever_issues_invoices_sends_them(role, send):
    ctx = ctx_for(role)
    send(manual(ctx), ctx, to=ANA)
    assert only_mail().to == [ANA]


def test_the_accountancy_firm_only_reads(send):
    invoice = manual()
    with pytest.raises(PermissionDenied):
        asked(invoice, ctx_for("hub_accountant"), to=ANA)
    send(invoice, to=ANA)
    assert [row.status for row in emails(invoice, ctx_for("hub_accountant")).emails] == ["sent"]


def test_an_employee_neither_sends_nor_sees_the_emails_of_someone_elses_invoice(make_user):
    invoice = manual()
    ctx = dataclasses.replace(ctx_for("hub_employee"), actor=make_user("eva", role="hub_employee"))
    for attempt in (lambda: asked(invoice, ctx, to=ANA), lambda: emails(invoice, ctx)):
        with pytest.raises(NotFound) as refused:
            attempt()
        assert refused.value.code == "invoice.not_found"


def test_addresses_reach_only_whoever_sees_the_customers_contact(customer, send):
    card = customer("Ana López", email=ANA)
    invoice = manual(customer_id=str(card.id))
    send(invoice)
    ctx = ctx_for("hub_admin")
    ctx = dataclasses.replace(ctx, permissions=ctx.permissions - {"base.view_customer_contact"})
    seen = emails(invoice, ctx)
    assert (seen.customer_email, [(row.to, row.status) for row in seen.emails]) == (None, [(None, "sent")])


def test_another_business_never_sees_them(hub_b, send):
    invoice = manual()
    send(invoice, to=ANA)
    with use_hub(hub_b):
        assert InvoiceEmail.objects.count() == 0
        with pytest.raises(NotFound):
            emails(invoice, ctx_for(scope=B))


# When it cannot be sent


def test_a_demo_sends_nothing():
    business(is_demo=True)
    with pytest.raises(Conflict) as refused:
        asked(manual(), to=ANA)
    assert refused.value.code == "invoice.email_demo"
    assert InvoiceEmail.objects.count() == 0


def test_a_business_with_nowhere_to_reply_sends_nothing():
    owned("")
    with pytest.raises(Conflict) as refused:
        asked(manual(), to=ANA)
    assert refused.value.code == "invoice.email_no_reply"
    assert InvoiceEmail.objects.count() == 0


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (smtplib.SMTPServerDisconnected("gone"), "invoice.email_unavailable"),
        (smtplib.SMTPRecipientsRefused({ANA: (550, b"No such user")}), "invoice.email_refused"),
    ],
)
def test_a_mail_that_does_not_leave_is_told_and_never_counts_as_sent(monkeypatch, send, failure, code):
    mail_server_fails(monkeypatch, failure)
    invoice = manual()
    out = send(invoice, to=ANA)
    email = kept(out)
    assert (email.status, email.sent_at, email.error_code) == ("failed", None, code)
    [row] = emails(invoice).emails
    assert row.status == "failed" and row.sent_at is None and row.reason
    assert events_of(events.EMAIL_SENT) == []
    [told] = events_of(events.EMAIL_FAILED)
    assert told == {"id": str(email.id), "invoice_id": str(invoice.id), "number": invoice.number}


def test_after_a_failure_it_can_be_sent_again(monkeypatch, send):
    invoice = manual()
    with monkeypatch.context() as failing:
        mail_server_fails(failing)
        send(invoice, to=ANA)
    send(invoice, to=ANA)
    assert [row.status for row in emails(invoice).emails] == ["sent", "failed"]


def test_without_its_pdf_nothing_leaves(monkeypatch, send):
    def missing(html):
        raise OSError("no pango")

    monkeypatch.setattr(pdf, "render_pdf", missing)
    out = send(manual(), to=ANA)
    assert (kept(out).status, kept(out).error_code, mail.outbox) == ("failed", "invoice.pdf_unavailable", [])


def test_an_invoice_whose_record_cannot_be_read_never_leaves_without_its_qr(monkeypatch, send):
    def unreadable(ctx, invoice):
        raise Conflict("unreadable", code="invoice.record_unreadable")

    monkeypatch.setattr(pdf_query, "qr_of", unreadable)
    out = send(manual(), to=ANA)
    assert (kept(out).status, kept(out).error_code, mail.outbox) == ("failed", "invoice.record_unreadable", [])


def test_what_nobody_foresaw_is_also_told_as_not_sent(monkeypatch, send):
    def broken(letter):
        raise RuntimeError("bug")

    monkeypatch.setattr(service.business_mail, "send", broken)
    out = send(manual(), to=ANA)
    assert (kept(out).status, kept(out).error_code) == ("failed", "invoice.email_unavailable")


def test_the_owner_left_meanwhile_and_there_is_nowhere_to_reply():
    out = asked(manual(), to=ANA)
    owned("")
    service.deliver(A, out.id)
    assert (kept(out).status, kept(out).error_code, mail.outbox) == ("failed", "invoice.email_no_reply", [])


def test_every_reason_is_said_in_the_readers_language():
    assert set(REASONS) == {
        "invoice.email_unavailable",
        "invoice.email_refused",
        "invoice.email_unconfirmed",
        "invoice.email_no_reply",
        "invoice.pdf_unavailable",
        "invoice.record_unreadable",
    }
    for code in REASONS:
        with translation.override("en"):
            english = reason_of(code)
        with translation.override("es"):
            assert english and reason_of(code) not in ("", english), code
    assert reason_of("") == ""
    assert reason_of("another.code") == str(REASONS["invoice.email_unavailable"])


# One delivery at a time


def test_a_delivery_is_taken_once(send):
    out = asked(manual(), to=ANA)
    service.deliver(A, out.id)
    service.deliver(A, out.id)
    assert (len(mail.outbox), kept(out).status) == (1, "sent")


def test_one_already_on_its_way_is_not_taken_again():
    out = asked(manual(), to=ANA)
    InvoiceEmail.objects.filter(pk=out.id).update(status="sending")
    service.deliver(A, out.id)
    assert (mail.outbox, kept(out).status) == ([], "sending")


def test_no_connection_waits_for_the_mail_server(monkeypatch, send):
    released: list[int] = []
    monkeypatch.setattr(outbound, "release", lambda: released.append(len(mail.outbox)))
    real = service.business_mail.send

    def late(letter):
        assert released == [0]
        real(letter)

    monkeypatch.setattr(service.business_mail, "send", late)
    out = send(manual(), to=ANA)
    assert kept(out).status == "sent"


def test_only_the_system_takes_and_ends_a_delivery():
    for name in ("invoice.email.claim", "invoice.email.record", "invoice.email.resume"):
        assert not ctx_for("hub_owner").has(get(name).permission), name
        assert not get(name).expose_api, name


# What it tells


def test_it_tells_the_request_and_the_end(send):
    invoice = manual()
    out = send(invoice, to=ANA)
    payload = {"id": str(out.id), "invoice_id": str(invoice.id), "number": invoice.number}
    assert events_of(events.EMAIL_REQUESTED) == [payload]
    assert events_of(events.EMAIL_SENT) == [payload]
    assert ANA not in str(list(OutboxEvent.objects.filter(name__startswith="invoice.email").values()))


def test_the_screen_follows_its_emails_and_the_customers_card():
    assert set(live_registry.subscribable["invoice.email.list"]) >= {
        events.EMAIL_REQUESTED,
        events.EMAIL_SENT,
        events.EMAIL_FAILED,
        "customer.customer.updated",
        "customer.customer.erased",
    }


def test_when_it_was_sent_is_the_moment_the_mail_server_took_it(at, send):
    at(NOON)
    out = send(manual(), to=ANA)
    [row] = emails(kept(out).invoice).emails
    assert row.sent_at == NOON[1]


def test_an_invoice_never_sent_has_no_emails():
    assert emails(manual()).emails == []


def test_the_assistant_asks_before_sending_and_no_automation_sends_alone():
    spec = get(SEND).ai_spec()
    assert spec.risk == "high"
    assert spec.preview["operation"] == "invoice.email.list"
    assert get(SEND).expose_api

