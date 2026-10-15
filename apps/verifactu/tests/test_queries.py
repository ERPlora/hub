"""The reads of the verifactu app (VERIFACTU-F12, F16–F19, F26, F27, F31): lists with their search, filters, order
and pages, a record's whole detail and why it waits, an invoice's record for the documents, the queue, the audit
trail searchable in both languages, the summaries, the chains and the configuration.

Cases from the current module's ``list_filters``, ``record_detail_fields``, ``events_list*`` and
``events_list_message_words``.
"""

import datetime as dt

import pytest
from django.utils import timezone, translation
from live.context import system_context

from apps.verifactu import queries
from apps.verifactu.models import (
    AeatRecord,
    Config,
    Event,
    OwnCertificate,
    Record,
    SendControl,
)
from apps.verifactu.tests.conftest import A, RECIPIENT, ctx_for, manual, run

pytestmark = pytest.mark.django_db


def ticket(price=1000):
    invoice = manual(
        [
            {
                "description": "Cut",
                "quantity": "1",
                "unit_price": price,
                "tax_rate": "21",
            }
        ],
        series_code="TICKET",
    )
    return Record.objects.get(
        pk=run("verifactu.record.create", {"invoice_id": str(invoice.id)}).record.id
    )


@pytest.fixture
def three(issuer):
    return [ticket(1000), ticket(2000), ticket(3000)]


def numbers(page) -> list[str]:
    return [row.invoice_number for row in page.rows]


# Records (VERIFACTU-F16)


def test_the_last_sealed_comes_first(three):
    page = run("verifactu.record.list")
    assert numbers(page) == [record.invoice_number for record in reversed(three)]
    assert (page.total, page.limit, page.offset) == (3, 50, 0)
    row = page.rows[0]
    assert (
        row.sequence,
        row.record_type,
        row.environment,
        row.status,
        row.total_amount,
    ) == (3, "alta", "testing", "pending", 3630)


def test_search_by_invoice_number_issuer_name_or_tax_id(three):
    assert numbers(run("verifactu.record.list", {"search": three[1].invoice_number})) == [three[1].invoice_number]
    assert run("verifactu.record.list", {"search": "B12345674"}).total == 3
    assert run("verifactu.record.list", {"search": "peluquería ana"}).total == 3
    assert run("verifactu.record.list", {"search": "nobody"}).total == 0


def test_a_sequence_number_alone_finds_its_record(three):
    assert [
        row.sequence for row in run("verifactu.record.list", {"search": "#2"}).rows
    ] == [2]


def test_filters_by_status_type_environment_dates_and_total(three):
    Record.objects.filter(pk=three[0].id).update(status="rejected")
    assert numbers(run("verifactu.record.list", {"status": "rejected"})) == [
        three[0].invoice_number
    ]
    assert run("verifactu.record.list", {"record_type": "anulacion"}).total == 0
    assert run("verifactu.record.list", {"invoice_type": "F2"}).total == 3
    assert run("verifactu.record.list", {"environment": "production"}).total == 0
    today = timezone.localdate()
    assert (
        run(
            "verifactu.record.list",
            {"issue_date_from": today.isoformat(), "issue_date_to": today.isoformat()},
        ).total
        == 3
    )
    assert (
        run(
            "verifactu.record.list",
            {"issue_date_from": (today + dt.timedelta(days=1)).isoformat()},
        ).total
        == 0
    )
    assert numbers(
        run(
            "verifactu.record.list",
            {"total_amount_from": 2000, "total_amount_to": 2500},
        )
    ) == [three[1].invoice_number]


def test_sort_by_a_column_with_a_stable_tie_break(three):
    assert [
        row.sequence
        for row in run("verifactu.record.list", {"sort": "sequence", "dir": "asc"}).rows
    ] == [1, 2, 3]
    assert [
        row.total_amount
        for row in run(
            "verifactu.record.list", {"sort": "total_amount", "dir": "desc"}
        ).rows
    ] == [3630, 2420, 1210]


def test_pages(three):
    page = run("verifactu.record.list", {"limit": 2, "offset": 2})
    assert (len(page.rows), page.total) == (1, 3)


# A record (VERIFACTU-F17, F18)


def test_a_record_is_read_whole_by_its_invoices_number(three):
    detail = run("verifactu.record.get", {"invoice_number": three[1].invoice_number})
    assert detail.id == three[1].id
    assert detail.previous_fingerprint == three[0].fingerprint
    assert detail.previous_number == three[0].invoice_number
    assert detail.fingerprint == three[1].fingerprint
    assert detail.qr_svg.startswith("data:image/svg+xml;base64,")
    assert (
        detail.can_transmit is True
        and detail.can_correct is False
        and detail.can_cancel is True
    )
    assert [event.kind for event in detail.events] == ["record_created"]
    assert detail.events[0].message.startswith("Registration record #2 sealed")


def test_a_record_that_waits_says_why(three, settings):
    settings.VERIFACTU_GATEWAY_URL = ""
    detail = run("verifactu.record.get", {"record_id": str(three[0].id)})
    assert {reason.code for reason in detail.waiting} == {"gateway_unavailable"}
    # Its XML was built when it was sealed: the submission it would go in can be read already.
    assert detail.envelope.startswith("<?xml")
    with translation.override("es"):
        detail = run(
            "verifactu.record.get",
            {"record_id": str(three[0].id)},
            ctx_for(language="es"),
        )
    assert "pasarela" in " ".join(reason.message for reason in detail.waiting)


def test_a_record_waiting_for_the_aeat_says_until_when(three, settings):
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    SendControl.objects.update(next_send_at=timezone.now() + dt.timedelta(seconds=40))
    detail = run("verifactu.record.get", {"record_id": str(three[0].id)})
    assert [reason.code for reason in detail.waiting] == ["aeat_wait"]
    assert detail.envelope.startswith(
        '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope'
    )


def test_a_record_in_the_aeat_does_not_wait(three):
    Record.objects.filter(pk=three[0].id).update(status="accepted", csv="A-1")
    detail = run("verifactu.record.get", {"record_id": str(three[0].id)})
    assert detail.waiting == []
    assert detail.can_transmit is False


def test_a_record_that_does_not_exist_is_not_found(issuer):
    from live.errors import NotFound

    with pytest.raises(NotFound):
        run("verifactu.record.get", {"invoice_number": "NOPE"})


def test_an_invoices_record_for_its_documents(issuer, invoice_does_not_seal):
    # ``ticket()`` seals by a direct call; ``other`` was issued while VeriFactu could not seal it yet.
    record = ticket()
    found = run("verifactu.record.by_invoice", {"invoice_id": str(record.invoice_id)})
    assert (found.record.id, found.record.qr_url, found.record.status) == (
        record.id,
        record.qr_url,
        "pending",
    )
    other = manual(**RECIPIENT)
    assert (
        run("verifactu.record.by_invoice", {"invoice_id": str(other.id)}).record is None
    )


# The queue (VERIFACTU-F20–F22)


def test_the_queue_is_what_is_not_in_the_aeat_yet(three):
    Record.objects.filter(pk=three[0].id).update(status="accepted")
    Record.objects.filter(pk=three[1].id).update(status="rejected")
    Record.objects.filter(pk=three[2].id).update(
        status="sent", attempts=2, wait_reason="unknown"
    )
    page = run("verifactu.contingency.list")
    assert numbers(page) == [three[2].invoice_number]
    row = page.rows[0]
    assert (row.attempts, row.status) == (2, "sent")
    assert row.last_error.startswith("the submission left and no answer came back")


def test_the_queue_is_searched_by_invoice_or_error(three):
    Record.objects.filter(pk=three[0].id).update(
        wait_reason="refused", wait_detail="Not the declared NIF."
    )
    assert numbers(run("verifactu.contingency.list", {"search": "declared NIF"})) == [
        three[0].invoice_number
    ]
    assert numbers(
        run("verifactu.contingency.list", {"search": three[1].invoice_number})
    ) == [three[1].invoice_number]


# The audit trail (VERIFACTU-F31)


def test_events_newest_first_in_the_readers_language(three):
    page = run("verifactu.event.list")
    assert page.total == 3
    assert (
        page.rows[0].message
        == f"Registration record #3 sealed for invoice {three[2].invoice_number}."
    )
    assert page.rows[0].invoice_number == three[2].invoice_number


def test_events_are_found_by_the_words_that_show_in_spanish_or_english(three):
    assert run("verifactu.event.list", {"search": "sealed"}).total == 3
    assert run("verifactu.event.list", {"search": "sellado"}).total == 3
    assert (
        run(
            "verifactu.event.list", {"search": f"sellado {three[0].invoice_number}"}
        ).total
        == 1
    )
    assert run("verifactu.event.list", {"search": "registro creado"}).total == 3


def test_events_filter_by_type_severity_and_day(three):
    Event.objects.create(
        kind="chain_broken", severity="critical", message_key="chain_broken", params={}
    )
    assert run("verifactu.event.list", {"kind": "chain_broken"}).total == 1
    assert run("verifactu.event.list", {"severity": "critical"}).total == 1
    today = timezone.localdate().isoformat()
    assert (
        run("verifactu.event.list", {"date_from": today, "date_to": today}).total == 4
    )


def test_a_row_the_catalogue_cannot_read_stays_listed(issuer):
    Event.objects.create(kind="config_changed", message_key="unknown_key", params={})
    assert run("verifactu.event.list").rows[0].message == "unknown_key"


# Summaries (VERIFACTU-F31, F32)


def test_the_compliance_summary_counts_what_is_not_in_the_aeat(three):
    Record.objects.filter(pk=three[0].id).update(status="accepted")
    Record.objects.filter(pk=three[1].id).update(status="rejected")
    summary = run("verifactu.stats.compliance_summary")
    assert (
        summary.unsent_count,
        summary.pending_count,
        summary.rejected_count,
        summary.accepted_count,
        summary.total,
    ) == (1, 2, 1, 1, 3)


def test_records_by_status_has_every_status(three):
    rows = run("verifactu.stats.records_by_status").rows
    assert [(row.status, row.total) for row in rows] == [
        ("pending", 3),
        ("sent", 0),
        ("accepted", 0),
        ("accepted_with_errors", 0),
        ("rejected", 0),
    ]
    assert rows[0].label == "Pending"


def test_the_queue_summary(three):
    summary = run("verifactu.stats.contingency_summary")
    assert (summary.queued_count, summary.overdue_count, summary.severity) == (
        3,
        3,
        "warning",
    )
    Record.objects.update(status="accepted")
    assert run("verifactu.stats.contingency_summary").severity == "ok"
    Record.objects.filter(pk=three[0].id).update(status="pending", attempts=3)
    assert run("verifactu.stats.contingency_summary").severity == "danger"


def test_the_latest_events(three):
    assert len(run("verifactu.stats.events_recent", {"limit": 2}).rows) == 2


# The chain and the AEAT's photo (VERIFACTU-F26, F27)


def test_the_chain_status_of_the_issuer(three):
    status = run("verifactu.chain.status")
    assert (status.issuer_nif, status.environment) == ("B12345674", "testing")
    [head] = status.chains
    assert (head.sequence, head.last_number, head.last_fingerprint, head.valid) == (
        3,
        three[2].invoice_number,
        three[2].fingerprint,
        None,
    )


def test_the_aeats_photo(issuer):
    AeatRecord.objects.create(
        issuer_nif="B12345674",
        environment="testing",
        invoice_number="T-1",
        fingerprint="A" * 64,
        state="Correcto",
    )
    page = run("verifactu.aeat_record.list")
    assert [row.invoice_number for row in page.rows] == ["T-1"]


# The configuration (VERIFACTU-F04, F08, F12, F34)


def test_the_configuration_starts_in_testing_through_erplora(issuer, settings):
    settings.SAAS_URL = "https://erplora.com"
    settings.VERIFACTU_GATEWAY_URL = ""
    config = run("verifactu.config.get")
    assert (
        config.environment,
        config.route,
        config.can_go_back,
        config.gateway_configured,
    ) == ("testing", "erplora", True, False)
    assert (config.issuer_nif, config.issuer_name) == ("B12345674", "Peluquería Ana SL")
    assert (
        config.declaration_url
        == "https://erplora.com/legal/declaracion-responsable/v1/"
    )
    assert config.account_url == "https://erplora.com"
    assert (
        config.producer.nif,
        config.producer.system_id,
        config.producer.installation,
        config.producer.multiple_ot,
    ) == (
        "B27593136",
        "EC",
        "a",
        "S",
    )
    assert config.synced_at is None
    assert {reason.code for reason in config.reasons} == {"gateway_unavailable"}


@pytest.mark.parametrize(
    ("env", "flag", "open_"),
    [("prod", True, True), ("prod", False, False), ("pre", True, False)],
)
def test_production_opens_only_in_prod_with_the_flag(settings, env, flag, open_):
    settings.ERPLORA_ENVIRONMENT = env
    settings.VERIFACTU_PRODUCTION_ENABLED = flag
    assert queries.production_open() is open_


def test_erplora_route_in_production_needs_approval_and_the_paid_option():
    config = Config(route="erplora", representation_status="approved", live_paid=False)
    assert queries.route_problem(config, "production") == "live_option_unpaid"
    config.live_paid = True
    assert queries.route_problem(config, "production") == ""
    config.representation_status = "submitted"
    assert queries.route_problem(config, "production") == "representation_not_approved"
    assert queries.route_problem(config, "testing") == ""


def test_what_was_sealed_leaves_without_the_live_option_but_never_without_a_way():
    # The live option keeps new sales from being sealed (route_problem); what was sealed goes to the AEAT while
    # the route can carry it (every ticket with a QR reaches the AEAT).
    config = Config(route="erplora", representation_status="approved", live_paid=False)
    assert queries.sending_problem(config, "production") == ""
    config.representation_status = "revoked"
    assert queries.sending_problem(config, "production") == "representation_not_approved"
    assert queries.sending_problem(config, "testing") == ""
    config.route = "own"
    assert queries.sending_problem(config, "testing") == "own_certificate_missing"


def test_the_configuration_says_why_new_sales_are_refused_only_in_production(issuer):
    assert run("verifactu.config.get").issue_blocker is None
    Config.objects.create(environment="production", representation_status="approved")
    blocker = run("verifactu.config.get").issue_blocker
    assert blocker.code == "live_option_unpaid"
    assert blocker.message.startswith("the live option of VeriFactu is not in your plan")
    Config.objects.update(live_paid=True)
    assert run("verifactu.config.get").issue_blocker is None


def own_certificate(days=30):
    return OwnCertificate.objects.create(
        holder="ANA LOPEZ",
        holder_tax_id="12345678Z",
        kind="personal",
        expires_at=timezone.now() + dt.timedelta(days=days),
        sealed_blob=b"sealed",
        uploaded_by="ana",
    )


def test_own_route_in_production_needs_only_its_valid_certificate():
    # As in the old Hub (an_own_certificate_needs_no_grant_to_go_live): the business files with its own
    # certificate, so neither ERPlora's approval nor the live option of the plan applies (Ioan's model,
    # 2026-10-15: «con certificado propio, como en el Hub antiguo»).
    config = Config(route="own", live_paid=False)
    assert queries.route_problem(config, "production") == "own_certificate_missing"
    own_certificate(days=-1)
    assert queries.route_problem(config, "production") == "own_certificate_missing"
    OwnCertificate.objects.all().delete()
    own_certificate()
    assert queries.route_problem(config, "production") == ""
    assert queries.route_problem(config, "testing") == ""


def test_the_configuration_lists_everything_that_keeps_it_from_going_live(issuer):
    assert [reason.code for reason in run("verifactu.config.get").live_blockers] == [
        "representation_not_approved",
        "live_option_unpaid",
    ]
    run(
        "verifactu.config.sync",
        {
            "version": 1,
            "live_paid": True,
            "hub_status": "past_due",
            "representation": {"status": "approved"},
        },
        system_context(A),
    )
    blockers = run("verifactu.config.get").live_blockers
    assert [reason.code for reason in blockers] == ["hub_not_active"]
    assert blockers[0].message
    run("verifactu.config.sync", {"version": 2, "hub_status": "active"}, system_context(A))
    assert run("verifactu.config.get").live_blockers == []


def test_with_the_own_certificate_the_live_option_is_not_asked(issuer):
    own_certificate()
    run("verifactu.config.update", {"route": "own"})
    assert run("verifactu.config.get").live_blockers == []
    run("verifactu.config.sync", {"version": 1, "hub_status": "suspended"}, system_context(A))
    assert [r.code for r in run("verifactu.config.get").live_blockers] == ["hub_not_active"]


def test_the_certificate_says_whose_it_is_and_when_it_expires(issuer):
    OwnCertificate.objects.create(
        holder="ANA LOPEZ",
        holder_tax_id="12345678Z",
        kind="personal",
        expires_at=timezone.now() + dt.timedelta(days=20, hours=1),
        sealed_blob=b"sealed",
        uploaded_by="ana",
    )
    certificate = run("verifactu.config.get").own_certificate
    assert (
        certificate.loaded,
        certificate.holder,
        certificate.holder_tax_id,
        certificate.kind,
        certificate.expires_in_days,
    ) == (True, "ANA LOPEZ", "12345678Z", "personal", 20)
    assert certificate.uploaded_at is not None
    assert "sealed" not in certificate.model_dump_json()


def test_without_a_certificate_it_says_not_loaded(issuer):
    certificate = run("verifactu.config.get").own_certificate
    assert (certificate.loaded, certificate.holder, certificate.expires_at) == (
        False,
        "",
        None,
    )


def test_with_a_production_record_it_cannot_go_back(three):
    Config.objects.update_or_create(singleton=True, defaults={"environment": "production"})
    Record.objects.filter(pk=three[0].id).update(environment="production")
    assert run("verifactu.config.get").can_go_back is False


def test_the_employee_reads_everything(three):
    employee = ctx_for("hub_employee")
    for name in (
        "verifactu.config.get",
        "verifactu.record.list",
        "verifactu.contingency.list",
        "verifactu.event.list",
        "verifactu.stats.compliance_summary",
        "verifactu.chain.status",
        "verifactu.aeat_record.list",
        "verifactu.diagnostic.last",
    ):
        run(name, {}, employee)


# Sorting the queue and the events (their tables sort on the server)


def test_the_queue_goes_out_order_by_default_and_sorts_by_a_column(three):
    Record.objects.filter(pk=three[0].id).update(attempts=5)
    assert numbers(run("verifactu.contingency.list")) == [record.invoice_number for record in three]
    by_attempts = run("verifactu.contingency.list", {"sort": "attempts", "dir": "desc"})
    assert numbers(by_attempts)[0] == three[0].invoice_number


def test_events_sort_by_when_type_or_severity(three):
    Event.objects.create(kind="chain_broken", severity="critical", message_key="chain_broken", params={})
    first = run("verifactu.event.list", {"sort": "severity", "dir": "desc"}).rows[0]
    assert first.severity == "critical"
    assert run("verifactu.event.list", {"sort": "created_at", "dir": "asc"}).rows[0].kind == "record_created"
