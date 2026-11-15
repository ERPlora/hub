"""Two businesses, each in its own database, invoicing under the same issuer's tax ID (VERIFACTU-F13, F15, F20).

Each one's chain of fingerprints starts at its own first record and goes on from its own last one, and each one's
queue sends its own records only: what one business sealed is never the previous record of the other's, nor goes out
with the other's pass.
"""

from apps.verifactu.models import Chain, Record
from apps.verifactu.tests.conftest import HUB_DB, ISSUER, B, answering, ctx_for, run

pytestmark = HUB_DB

FIRST = "<sum1:PrimerRegistro>S</sum1:PrimerRegistro>"


def sealed(unit_price: int, ctx=None) -> Record:
    """A ticket of ``unit_price`` cents issued in the business at work, with its record sealed at the emission."""
    lines = [{"description": "Cut", "quantity": "1", "unit_price": unit_price, "tax_rate": "21"}]
    invoice = run("invoice.invoice.create", {"series_code": "TICKET", "lines": lines}, ctx)
    return Record.objects.get(invoice_id=invoice.id)


def test_each_business_chains_its_records_from_its_own_first_one(issuer, in_business_b):
    first_in_a = sealed(1000)
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
        first_in_b = sealed(2000, ctx_for(scope=B))
        second_in_b = sealed(3000, ctx_for(scope=B))
        head_of_b = Chain.objects.get()
    second_in_a = sealed(4000)

    assert (first_in_b.sequence, first_in_b.previous_fingerprint) == (1, "")
    assert FIRST in first_in_b.xml
    assert (second_in_b.sequence, second_in_b.previous_fingerprint) == (2, first_in_b.fingerprint)
    assert (second_in_a.sequence, second_in_a.previous_fingerprint) == (2, first_in_a.fingerprint)
    assert (head_of_b.sequence, head_of_b.last_fingerprint) == (2, second_in_b.fingerprint)
    assert (Chain.objects.get().sequence, Chain.objects.get().last_fingerprint) == (2, second_in_a.fingerprint)


def test_each_business_sends_its_own_queue_only(issuer, in_business_b, gateway_answers):
    gateway_answers.set(answering())
    in_a = sealed(1000)
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
        in_b = sealed(2000, ctx_for(scope=B))
        sent = run("verifactu.contingency.process", {}, ctx_for(scope=B))
        status_in_b = Record.objects.get(pk=in_b.pk).status

    assert (sent.sent, sent.accepted) == (1, 1)
    [(_, payload)] = gateway_answers.calls
    assert payload["hub"] == B.key
    assert in_b.fingerprint in payload["envelope"]
    assert in_a.fingerprint not in payload["envelope"]
    assert status_in_b == Record.Status.ACCEPTED
    assert Record.objects.get(pk=in_a.pk).status == Record.Status.PENDING
