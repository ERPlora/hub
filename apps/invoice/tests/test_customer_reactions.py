"""A customer whose personal data is erased (GDPR): the log of the emails of their invoices keeps no address of theirs."""

import pytest
from django.core import mail

from apps.invoice import events
from apps.invoice.models import Invoice
from apps.invoice.services import emails as service
from apps.invoice.tests.conftest import A, HUB_DB, deliver, run
from apps.invoice.tests.emailed import ANA, asked, emails, kept, owner, send
from apps.invoice.tests.manual import manual

__all__ = ["owner", "send"]

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "owner")]


@pytest.fixture
def ana(customer):
    return customer("Ana López", email=ANA, tax_id="12345678Z", address="Calle Luna 3")


def erased(card) -> None:
    run("customer.customer.erase", {"id": str(card.id), "reason": "She asked for it"})
    deliver("customer.customer.erased")


def test_the_addresses_go_and_the_rest_of_the_log_stays(ana, send):
    invoice = manual(customer_id=str(ana.id))
    out = send(invoice, to="other@example.com")
    before = Invoice.objects.filter(pk=invoice.id).values().get()
    erased(ana)
    email = kept(out)
    assert (email.to_address, email.status, email.sent_at is not None) == ("", "sent", True)
    assert emails(invoice).customer_email == ""
    assert Invoice.objects.filter(pk=invoice.id).values().get() == before


def test_the_emails_of_another_customer_keep_theirs(ana, customer, send):
    luis = customer("Luis Gil", email="luis@example.com", tax_id="87654321X", address="Calle Sol 1")
    out = send(manual(customer_id=str(luis.id)))
    erased(ana)
    assert kept(out).to_address == "luis@example.com"


def test_one_that_had_not_left_is_told_as_not_sent(ana):
    out = asked(manual(customer_id=str(ana.id)))
    erased(ana)
    service.deliver(A, out.id)
    assert (kept(out).status, kept(out).error_code, mail.outbox) == ("failed", "invoice.email_unavailable", [])


def test_a_second_notice_changes_nothing(ana, send):
    send(manual(customer_id=str(ana.id)))
    erased(ana)
    assert deliver("customer.customer.erased").forgotten == 0


def test_it_is_the_reaction_to_customers():
    assert events.REACTIONS["customer.customer.erased"] == "invoice.email.forget_customer"
