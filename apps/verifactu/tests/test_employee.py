"""The employee of a business, as the role comes: sees everything the business sends to the AEAT and sends again what
has not gone out (VERIFACTU-F10, F16, F17, F21, F22, F25, F27, F35), but changes nothing: neither corrects nor cancels
a record (F24, F30) nor configures VeriFactu.

What the AEAT answers is its real answer (``fixtures/``); only the SaaS's gateway transport is stood in for
(``gateway_answers``).
"""

import pytest
from django.utils import timezone
from live.errors import PermissionDenied
from live.operations import registry

from apps.verifactu import gateway
from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import HUB_DB, aeat_holds, answering, ctx_for, run

pytestmark = HUB_DB

CHANGES = ("verifactu.correct_record", "verifactu.configure")


def employee():
    return ctx_for("hub_employee", actor="bea")


def sealed(ctx=None) -> Record:
    """The record of a one-line ticket issued with ``ctx``'s session."""
    lines = [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]
    invoice = run("invoice.invoice.create", {"lines": lines, "series_code": "TICKET"}, ctx)
    return Record.objects.get(pk=run("verifactu.record.create", {"invoice_id": str(invoice.id)}, ctx).record.id)


def waiting(gateway_answers) -> Record:
    """A record the AEAT could not be reached for: in the queue, to send again."""
    gateway_answers.set(gateway.Reply(kind=gateway.UNREACHABLE, message="down"))
    record = sealed()
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert record.status == "pending"
    return record


def test_the_employee_lists_every_record_of_the_business_not_only_their_own(issuer):
    by_owner = sealed(ctx_for("hub_owner", actor="olga"))
    by_colleague = sealed(ctx_for("hub_employee", actor="eva"))
    listed = run("verifactu.record.list", {}, employee())
    assert {row.invoice_number for row in listed.rows} == {by_owner.invoice_number, by_colleague.invoice_number}
    assert run("verifactu.record.get", {"record_id": str(by_owner.id)}, employee()).invoice_number == (
        by_owner.invoice_number
    )


def test_the_employee_sends_a_record_now(issuer, gateway_answers):
    record = waiting(gateway_answers)
    gateway_answers.set(answering())
    run("verifactu.record.transmit", {"record_id": str(record.id)}, employee())
    record.refresh_from_db()
    assert record.status == "accepted"


def test_the_employee_retries_an_entry_and_processes_the_queue(issuer, gateway_answers):
    record = waiting(gateway_answers)
    run("verifactu.contingency.retry", {"record_id": str(record.id)}, employee())
    record.refresh_from_db()
    assert record.next_attempt_at <= timezone.now()
    gateway_answers.set(answering())
    run("verifactu.contingency.process", {}, employee())
    record.refresh_from_db()
    assert record.status == "accepted"


def test_the_employee_asks_the_aeat_whether_it_holds_a_record_of_the_queue(issuer, gateway_answers):
    gateway_answers.set(gateway.Reply(kind=gateway.UNKNOWN, message="read timeout"))
    record = sealed()
    run("verifactu.contingency.process")
    record.refresh_from_db()
    gateway_answers.set(aeat_holds(record))
    result = run("verifactu.record.reconcile", {"record_id": str(record.id)}, employee())
    assert (result.held, result.record.status) == (True, "accepted")


def test_the_employee_queries_the_aeat_and_tests_the_connection(issuer, gateway_answers):
    gateway_answers.set(aeat_holds())
    assert run("verifactu.aeat.query", {"year": 2026, "month": 8}, employee()).count == 4
    gateway_answers.set(gateway.Reply(kind=gateway.ANSWERED, ready=True, message="Ready."))
    assert run("verifactu.diagnostic.run", {}, employee()).can_send is True


def test_the_employee_neither_corrects_nor_cancels_a_record(issuer):
    record = sealed()
    with pytest.raises(PermissionDenied):
        run("verifactu.record.correct", {"record_id": str(record.id)}, employee())
    with pytest.raises(PermissionDenied):
        run("verifactu.record.cancel", {"record_id": str(record.id), "reason": "by mistake"}, employee())


@pytest.mark.parametrize(
    "name",
    ["verifactu.config.go_live", "verifactu.config.back_to_testing", "verifactu.test_invoice.create",
     "verifactu.certificate.remove"],
)
def test_the_employee_configures_nothing(issuer, name):
    with pytest.raises(PermissionDenied):
        run(name, {}, employee())


def test_no_operation_that_corrects_or_configures_is_the_employee_s():
    changing = sorted(name for name, op in registry.items() if op.app_label == "verifactu" and op.permission in CHANGES)
    assert {"verifactu.record.correct", "verifactu.chain.recover_from_aeat", "verifactu.certificate.upload"} <= set(
        changing
    )
    assert [name for name in changing if employee().has(registry[name].permission)] == []
