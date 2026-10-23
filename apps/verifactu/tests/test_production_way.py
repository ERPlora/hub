"""Production only seals what can reach the AEAT, and nothing leaves a server ERPlora has not opened (working-rules §15).

From the review of the fiscal block (2026-10-15). The server's lock (``VERIFACTU_PRODUCTION_ENABLED``) holds every record
of production before the gateway is called, and Settings says it where they say what else is missing. In production an
own certificate this server cannot open (its key missing or rotated), a server without ERPlora's gateway and a closed
server are no way to the AEAT: going live is refused, and so is every new sale or invoice, as a route without its
authorisation or its certificate is. Testing refuses nothing.
"""

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import Conflict

from apps.invoice.models import Invoice, InvoiceSeries
from apps.verifactu import certificates, queries
from apps.verifactu.models import Chain, Config, Environment, Record
from apps.verifactu.tests.conftest import (
    A,
    answering,
    b64,
    ctx_for,
    make_p12,
    manual,
    run,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway and the key that keeps the own certificates."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


def code_of(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    return refused.value.code


def ticket():
    return manual(
        [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
        series_code="TICKET",
    )


def by_erplora(*, live: bool = False):
    run(
        "verifactu.config.sync",
        {"version": 1, "representation": {"status": "approved"}},
        system_context(A),
    )
    if live:
        run("verifactu.config.go_live")


def by_own_certificate(*, live: bool = False):
    run(
        "verifactu.certificate.upload",
        {"p12_base64": b64(make_p12()), "password": "secret"},
    )
    run("verifactu.config.update", {"route": "own"})
    if live:
        run("verifactu.config.go_live")


def lose_the_key(settings, how: str) -> None:
    settings.FISCAL_CERTIFICATE_KEY = (
        "" if how == "missing" else certificates.generate_key()
    )


def codes(waits) -> set[str]:
    return {wait.code for wait in waits}


def nothing_new_was_issued(invoices: int = 0, records: int = 0) -> None:
    assert Invoice.objects.count() == invoices
    assert Record.objects.count() == records
    assert (
        sum(InvoiceSeries.objects.values_list("current_number", flat=True)) == invoices
    )


# ── The server's lock ────────────────────────────────────────────────────────────────────────────


def test_a_record_of_production_waits_while_the_server_is_closed(
    issuer, opened, gateway_answers
):
    by_erplora(live=True)
    record = Record.objects.get(invoice_id=ticket().id)
    assert record.environment == Environment.PRODUCTION
    opened.VERIFACTU_PRODUCTION_ENABLED = False

    out = run("verifactu.contingency.process")

    assert (out.sent, out.reason) == (0, "production_closed")
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == ("pending", "production_closed")
    assert gateway_answers.calls == []
    assert (
        code_of(lambda: run("verifactu.record.transmit", {"record_id": str(record.id)}))
        == "verifactu.production_closed"
    )
    assert gateway_answers.calls == []
    detail = run("verifactu.record.get", {"record_id": str(record.id)})
    assert "production_closed" in codes(detail.waiting)


def test_it_goes_out_as_soon_as_the_server_opens_again(issuer, opened, gateway_answers):
    by_erplora(live=True)
    record = Record.objects.get(invoice_id=ticket().id)
    opened.VERIFACTU_PRODUCTION_ENABLED = False
    run("verifactu.contingency.process")
    opened.VERIFACTU_PRODUCTION_ENABLED = True
    gateway_answers.set(answering())

    run("verifactu.contingency.process")

    record.refresh_from_db()
    assert record.status == "accepted"


def test_a_closed_server_issues_nothing_new_in_production(issuer, opened):
    by_erplora(live=True)
    opened.VERIFACTU_PRODUCTION_ENABLED = False

    with pytest.raises(Conflict) as refused:
        ticket()

    assert refused.value.code == "verifactu.production_closed"
    assert str(refused.value).startswith("Nothing was issued")
    nothing_new_was_issued()


def test_settings_say_the_closed_server_where_they_say_what_else_is_missing(
    issuer, settings
):
    settings.VERIFACTU_PRODUCTION_ENABLED = False

    config = run("verifactu.config.get")

    blockers = {wait.code: wait.message for wait in config.live_blockers}
    assert "has not opened" in blockers["production_closed"]
    with translation.override("es"):
        config = run("verifactu.config.get", {}, ctx_for(language="es"))
    blockers = {wait.code: wait.message for wait in config.live_blockers}
    assert "no ha abierto" in blockers["production_closed"]


def test_in_production_settings_say_the_closed_server_stops_new_documents(
    issuer, opened
):
    by_erplora(live=True)
    opened.VERIFACTU_PRODUCTION_ENABLED = False

    config = run("verifactu.config.get")

    assert config.issue_blocker.code == "production_closed"
    assert "production_closed" in codes(config.reasons)
    assert config.route_ready is False


# ── An own certificate this server cannot open ──────────────────────────────────────────────────


@pytest.mark.parametrize("how", ["missing", "rotated"])
def test_an_unreadable_own_certificate_is_no_way_to_production(issuer, opened, how):
    by_own_certificate()
    lose_the_key(opened, how)
    config = queries.config_row()

    assert (
        queries.route_problem(config, Environment.PRODUCTION, A)
        == "own_certificate_unreadable"
    )
    assert queries.route_problem(config, Environment.TESTING, A) == ""
    assert "own_certificate_unreadable" in codes(
        run("verifactu.config.get").live_blockers
    )
    assert (
        code_of(lambda: run("verifactu.config.go_live"))
        == "verifactu.own_certificate_unreadable"
    )
    assert Config.objects.get().environment == Environment.TESTING


@pytest.mark.parametrize("how", ["missing", "rotated"])
def test_in_production_an_unreadable_certificate_issues_nothing_new(
    issuer, opened, how
):
    by_own_certificate(live=True)
    ticket()
    lose_the_key(opened, how)

    with pytest.raises(Conflict) as refused:
        ticket()

    assert refused.value.code == "verifactu.own_certificate_unreadable"
    nothing_new_was_issued(invoices=1, records=1)
    assert (
        run("verifactu.config.get").issue_blocker.code == "own_certificate_unreadable"
    )


def test_in_production_an_unreadable_certificate_seals_and_numbers_no_record(
    issuer, opened, invoice_does_not_seal
):
    by_own_certificate(live=True)
    invoice = ticket()
    lose_the_key(opened, "rotated")

    assert (
        code_of(lambda: run("verifactu.record.create", {"invoice_id": str(invoice.id)}))
        == "verifactu.own_certificate_unreadable"
    )
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


# ── A server without ERPlora's gateway ──────────────────────────────────────────────────────────


def test_without_the_gateway_production_has_no_way_to_the_aeat(issuer, opened):
    by_erplora()
    opened.VERIFACTU_GATEWAY_URL = ""
    config = queries.config_row()

    assert (
        queries.route_problem(config, Environment.PRODUCTION, A) == "gateway_unavailable"
    )
    assert queries.route_problem(config, Environment.TESTING, A) == ""
    assert "gateway_unavailable" in codes(run("verifactu.config.get").live_blockers)
    assert (
        code_of(lambda: run("verifactu.config.go_live"))
        == "verifactu.gateway_unavailable"
    )
    assert Config.objects.get().environment == Environment.TESTING


def test_in_production_without_the_gateway_nothing_new_is_issued(issuer, opened):
    by_erplora(live=True)
    opened.VERIFACTU_GATEWAY_URL = ""

    with pytest.raises(Conflict) as refused:
        ticket()

    assert refused.value.code == "verifactu.gateway_unavailable"
    assert str(refused.value).startswith("Nothing was issued")
    nothing_new_was_issued()


# ── Testing refuses nothing ─────────────────────────────────────────────────────────────────────


def test_testing_still_issues_without_the_key_the_gateway_or_the_opening(
    issuer, opened
):
    by_own_certificate()
    lose_the_key(opened, "missing")
    opened.VERIFACTU_GATEWAY_URL = ""
    opened.VERIFACTU_PRODUCTION_ENABLED = False

    invoice = ticket()

    record = Record.objects.get(invoice_id=invoice.id)
    assert (record.environment, record.status) == (Environment.TESTING, "pending")
    assert run("verifactu.config.get").issue_blocker is None
