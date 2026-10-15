"""ERPlora's invoices issued by its platform hub (PLAN-SAAS §4; contract point 4): ``invoice.invoice.issue_platform``
writes the invoice and its VeriFactu record in one transaction, idempotent by the SaaS's id (``platform_ref``);
``invoice.invoice.platform_status`` answers how it stands, ``invoice.invoice.platform_document`` its A4 and
``invoice.invoice.platform_health`` whether the platform hub can issue now. Real VeriFactu, no mocks.

The case lists come from the old SaaS's own engine (billing/tests/test_hub_invoices.py, test_invoice_dedup.py,
test_invoice_environment.py; hubs/main/tests/test_platform.py): one invoice per Stripe invoice whatever the
deliveries, the environment by deployment, the QR only from a record.
"""

import copy
import threading

import pytest
from django.db import connection
from live.context import Scope, system_context
from live.errors import OperationError

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import run
from apps.invoice.tests.test_platform import BODY, CREDIT_NOTE, line
from apps.verifactu.models import Config, Record

PLATFORM = Scope("host", "erplora")
#: ERPlora's identity with a test tax ID (never the real seal's NIF in a test).
PLATFORM_ISSUER = {
    "legal_name": "ERPLORA CLOUD SL",
    "tax_id": "B12345674",
    "address": "Avda. de Lisboa, 17, 2º C",
    "postal_code": "28822",
    "city": "Coslada",
    "province": "Madrid",
}
AEAT_QR = "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?"


def system():
    return system_context(PLATFORM)


def issue(body: dict | None = None):
    return run("invoice.invoice.issue_platform", body or copy.deepcopy(BODY), system())


def status(platform_ref: str = BODY["id"]):
    return run("invoice.invoice.platform_status", {"id": platform_ref}, system())


def code_of(call) -> str:
    with pytest.raises(OperationError) as failed:
        call()
    return failed.value.code


@pytest.fixture
def platform_hub(db, settings):
    """ERPlora's own hub: its slug, its issuer (Invoicing → Issuer) and ERPlora's route; the pre deployment."""
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.ERPLORA_ENVIRONMENT = "pre"
    run("invoice.issuer.update", PLATFORM_ISSUER, system())
    return PLATFORM


def test_it_issues_the_invoice_and_its_record_in_one_go(platform_hub):
    answer = issue()

    invoice = Invoice.objects.get(platform_ref=BODY["id"])
    record = Record.objects.get(invoice=invoice)
    assert (answer.status, answer.qr, answer.error, answer.already) == (
        "issued",
        record.qr_url,
        None,
        False,
    )
    assert answer.qr.startswith(AEAT_QR)
    assert (
        invoice.number,
        invoice.series_code,
        invoice.sequence,
        invoice.invoice_type,
    ) == (
        "ERP-2026-00123",
        "ERP",
        123,
        "F1",
    )
    assert (invoice.issuer_name, invoice.issuer_tax_id) == (
        "ERPLORA CLOUD SL",
        "B12345674",
    )
    assert (invoice.base_amount, invoice.tax_amount, invoice.total_amount) == (
        2999,
        630,
        3629,
    )
    assert str(invoice.issue_date) == "2026-10-15"
    assert record.issuer_nif == "B12345674"
    assert record.invoice_number == "ERP-2026-00123"


def test_the_number_is_the_saas_own_and_no_series_counts_for_it(platform_hub):
    issue()

    series = InvoiceSeries.objects.get(code="ERP", year=2026)
    assert series.current_number == 0
    assert Invoice.objects.get().series == series


def test_a_second_delivery_answers_what_the_first_issued(platform_hub):
    first = issue()

    second = issue()

    assert second.already is True
    assert (second.status, second.qr, second.error) == (first.status, first.qr, None)
    assert Invoice.objects.count() == 1
    assert Record.objects.count() == 1


def test_a_number_another_invoice_holds_is_refused(platform_hub):
    issue()
    other = {**copy.deepcopy(BODY), "id": "019a0000-0000-7000-8000-0000000000ff"}

    assert code_of(lambda: issue(other)) == "invoice.number_taken"
    assert Invoice.objects.count() == 1


def test_a_credit_note_rectifies_the_invoice_of_the_saas_it_names(platform_hub):
    issue()

    answer = issue({**copy.deepcopy(BODY), **copy.deepcopy(CREDIT_NOTE)})

    original = Invoice.objects.get(platform_ref=BODY["id"])
    credit = Invoice.objects.get(platform_ref=CREDIT_NOTE["id"])
    assert answer.status == "issued"
    assert (
        credit.invoice_type,
        credit.rectifies,
        credit.rectification_kind,
        credit.series_code,
    ) == (
        "R1",
        original,
        "I",
        "ERPR",
    )
    assert credit.total_amount == -3629
    # Nothing is left of the original: cancelled, as Invoicing's own rectifications leave it.
    original.refresh_from_db()
    assert original.status == Invoice.Status.CANCELLED
    assert Record.objects.get(invoice=credit).invoice_type == "R1"


def test_a_credit_note_of_an_invoice_the_hub_never_issued_is_404(platform_hub):
    body = {**copy.deepcopy(BODY), **copy.deepcopy(CREDIT_NOTE)}

    assert code_of(lambda: issue(body)) == "invoice.platform_original_unknown"
    assert Invoice.objects.count() == 0


def test_above_400_euros_without_a_tax_id_nothing_is_issued(platform_hub):
    body = copy.deepcopy(BODY)
    body["recipient"]["tax_id"] = ""
    body["lines"] = [line(net_cents=34710, tax_cents=7289, total_cents=41999)]
    body.update(net_cents=34710, tax_cents=7289, total_cents=41999)

    assert code_of(lambda: issue(body)) == "invoice.platform_recipient_required"
    assert Invoice.objects.count() == 0


def test_a_body_out_of_shape_is_refused_with_its_reason(platform_hub):
    body = copy.deepcopy(BODY)
    body["tax_treatment"] = "mystery"
    body["lines"][0]["tax_treatment"] = "mystery"

    with pytest.raises(OperationError) as refused:
        issue(body)

    assert (refused.value.status, refused.value.code) == (
        422,
        "invoice.platform_tax_treatment_unknown",
    )
    assert "mystery" in refused.value.message


def test_a_refusal_of_verifactu_undoes_the_invoice(platform_hub):
    # VeriFactu cannot declare an operation without its description: its 409 undoes the whole issue.
    body = copy.deepcopy(BODY)
    body["lines"][0]["description"] = ""

    assert code_of(lambda: issue(body)).startswith("verifactu.")
    assert Invoice.objects.count() == 0
    assert Record.objects.count() == 0


def test_in_pre_the_record_files_in_testing(platform_hub, settings):
    settings.ERPLORA_ENVIRONMENT = "pre"

    issue()

    assert Record.objects.get().environment == Record.Environment.TESTING


def test_in_prod_the_record_files_in_production_whatever_the_configuration_says(
    platform_hub, settings
):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    assert Config.objects.filter(environment=Config.Environment.PRODUCTION).count() == 0

    issue()

    assert Record.objects.get().environment == Record.Environment.PRODUCTION


def test_in_prod_while_erplora_has_not_opened_real_filing_it_files_in_testing(
    platform_hub, settings
):
    # Working-rules §15: ERPlora's own invoices skip no lock.
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = False

    issue()

    assert Record.objects.get().environment == Record.Environment.TESTING


def test_an_invoice_without_its_record_yet_is_issuing_and_then_issued(
    platform_hub, monkeypatch
):
    from live.operations import UnknownOperation

    from apps.invoice import services as invoicing

    real = invoicing.get_operation

    def without_verifactu(name):
        if name == invoicing.VERIFACTU_RECORD:
            raise UnknownOperation(name)
        return real(name)

    monkeypatch.setattr(invoicing, "get_operation", without_verifactu)
    assert issue().status == "issuing"
    assert status().status == "issuing"
    monkeypatch.undo()

    invoice = Invoice.objects.get()
    run("verifactu.record.create", {"invoice_id": str(invoice.id)}, system())

    assert status().status == "issued"


@pytest.mark.parametrize("aeat", ["accepted", "accepted_with_errors", "rejected"])
def test_its_status_follows_its_record(platform_hub, aeat):
    issue()
    Record.objects.update(
        status=aeat, aeat_code="1100" if aeat != "accepted" else "", aeat_message="Bad"
    )

    answer = status()

    assert answer.status == aeat
    assert answer.qr.startswith(AEAT_QR)
    if aeat == "accepted":
        assert answer.error is None
    else:
        assert answer.error.model_dump() == {"code": "1100", "message": "Bad"}


def test_the_status_of_an_invoice_it_never_issued_is_404(platform_hub):
    assert code_of(status) == "invoice.platform_unknown"


def test_its_document_is_the_a4_of_invoicing_with_its_qr_once_the_aeat_accepted_it(
    platform_hub,
):
    issue()
    document = run("invoice.invoice.platform_document", {"id": BODY["id"]}, system())

    # In the document's language (the SaaS's ``language``), and without a QR the AEAT cannot vouch for yet.
    assert document.number == "ERP-2026-00123"
    assert "ERPLORA CLOUD SL" in document.html and "Factura" in document.html
    assert "QR tributario" not in document.html

    Record.objects.update(status="accepted")
    accepted = run("invoice.invoice.platform_document", {"id": BODY["id"]}, system())

    assert "QR tributario" in accepted.html
    assert "VERI*FACTU" in accepted.html
    assert "data:image/svg+xml" in accepted.html


def test_the_document_of_an_invoice_it_never_issued_is_404(platform_hub):
    assert (
        code_of(
            lambda: run(
                "invoice.invoice.platform_document", {"id": BODY["id"]}, system()
            )
        )
        == "invoice.platform_unknown"
    )


def test_it_is_healthy_only_with_its_issuer(db, settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key

    unconfigured = run("invoice.invoice.platform_health", {}, system())
    run("invoice.issuer.update", PLATFORM_ISSUER, system())
    configured = run("invoice.invoice.platform_health", {}, system())

    assert (unconfigured.ready, configured.ready) == (False, True)
    assert unconfigured.detail
    assert configured.detail == ""


# ── Two deliveries at once (Review Focus 4: the reconcile of the SaaS posting again) ────────────────


@pytest.fixture
def committed_platform_hub(transactional_db, settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.ERPLORA_ENVIRONMENT = "pre"
    run("invoice.issuer.update", PLATFORM_ISSUER, system())


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


@pytest.mark.django_db(transaction=True)
def test_the_same_invoice_delivered_twice_at_once_is_one_invoice_and_one_record(
    committed_platform_hub,
):
    first, second = at_once(issue, issue)

    assert not isinstance(first, Exception), first
    assert not isinstance(second, Exception), second
    assert sorted([first.already, second.already]) == [False, True]
    assert first.qr == second.qr
    assert Invoice.objects.count() == 1
    assert Record.objects.count() == 1
