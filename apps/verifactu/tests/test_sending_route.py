"""The route a business files by is worked out, never chosen: with its own certificate loaded and in force, the
certificate; without one, ERPlora's seal while it is in testing, demos included. Going live needs that certificate or,
where ERPlora files on behalf of businesses (``VERIFACTU_ERPLORA_ROUTE_ENABLED``), the approved signed authorisation;
with both, the certificate wins. Going live keeps the route of that moment in ``Config.route``, and from then on the
business sends, asks the AEAT and cancels by it whatever happens to the certificate. ERPlora's own hub (the business
``B`` here) always files with the seal.
"""

import datetime as dt

import pytest
from django.utils import timezone

from apps.verifactu import certificates, gateway
from apps.verifactu.models import Config, Environment, OwnCertificate, Record, SendControl
from apps.verifactu.tests.conftest import (
    HUB_DB,
    ISSUER,
    A,
    B,
    accepted_by_the_aeat_of_testing,
    aeat_holds,
    answering,
    b64,
    codes,
    ctx_for,
    make_p12,
    run,
    ticket,
)
from base.models import Hub
from live.context import system_context
from live.errors import Conflict

pytestmark = HUB_DB

SAAS = "http://saas.internal:8001"
PLATFORM = B
DEMO = B


@pytest.fixture(autouse=True)
def certificates_kept(settings):
    """The key that keeps the own certificates set, and ERPlora's route open unless a test closes it."""
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = True
    return settings


@pytest.fixture(params=[True, False], ids=["erplora_route_on", "erplora_route_off"])
def switch(certificates_kept, request):
    """Each test that takes it runs with ERPlora's route open to businesses and closed to them."""
    certificates_kept.VERIFACTU_ERPLORA_ROUTE_ENABLED = request.param
    return request.param


@pytest.fixture
def opened(certificates_kept, gateway_answers):
    """The prod deployment opened by ERPlora, with its gateway answering every record as accepted."""
    certificates_kept.ERPLORA_ENVIRONMENT = "prod"
    certificates_kept.VERIFACTU_PRODUCTION_ENABLED = True
    gateway_answers.set(answering())
    return certificates_kept


def upload_certificate(scope=A) -> None:
    run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"}, ctx_for(scope=scope))
    accepted_by_the_aeat_of_testing()


def approve(scope=A) -> None:
    run("verifactu.config.sync", {"version": 1, "representation": {"status": "approved"}}, system_context(scope))


def config(scope=A):
    return run("verifactu.config.get", ctx=ctx_for(scope=scope))


def process(scope=A) -> None:
    SendControl.objects.update(next_send_at=None)
    run("verifactu.contingency.process", ctx=ctx_for(scope=scope))


def calls(gateway_answers, path: str = gateway.SUBMIT_PATH) -> list[tuple[str, str, bool]]:
    """Each call to the gateway at ``path``: its route, its environment and whether a certificate travelled."""
    return [
        (payload["route"], payload["environment"], "certificate" in payload)
        for called, payload in gateway_answers.calls
        if called == path
    ]


def refused_with_409(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    assert refused.value.status == 409
    return refused.value.code


# ── In testing the route follows the certificate ─────────────────────────────────────────────────


def test_in_testing_a_valid_own_certificate_files_with_it_and_nothing_asks_for_it(issuer, gateway_answers, switch):
    gateway_answers.set(answering())
    upload_certificate()

    out = config()
    assert out.route == "own"
    assert out.route_ready_for_production is True
    assert "own_certificate_required" not in codes(out.live_blockers)
    record = Record.objects.get(invoice_id=ticket().id)
    process()

    assert calls(gateway_answers) == [("own", "testing", True)]
    record.refresh_from_db()
    assert record.status == Record.Status.ACCEPTED
    gateway_answers.set(gateway.Reply(kind=gateway.ANSWERED, ready=True, message="Ready."))
    assert run("verifactu.diagnostic.run").route == "own"
    assert calls(gateway_answers, gateway.PROBE_PATH) == [("own", "testing", True)]


def test_in_testing_without_a_certificate_the_seal_files(issuer, gateway_answers, switch):
    gateway_answers.set(answering())

    assert config().route == "erplora"
    ticket()
    process()

    assert calls(gateway_answers) == [("erplora", "testing", False)]


def test_removing_the_certificate_in_testing_puts_what_it_refused_back_out_with_the_seal(
    issuer, gateway_answers, switch
):
    upload_certificate()
    gateway_answers.set(gateway.Reply(kind=gateway.REFUSED, code="verifactu_gateway.certificate_invalid", message="No."))
    record = Record.objects.get(invoice_id=ticket().id)
    process()
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == (Record.Status.PENDING, "refused")

    run("verifactu.certificate.remove")
    gateway_answers.set(answering())
    process()

    assert config().route == "erplora"
    assert calls(gateway_answers) == [("own", "testing", True), ("erplora", "testing", False)]
    record.refresh_from_db()
    assert record.status == Record.Status.ACCEPTED


def test_an_expired_certificate_in_testing_leaves_the_seal_to_file(issuer, gateway_answers, switch):
    gateway_answers.set(answering())
    upload_certificate()
    OwnCertificate.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))

    assert config().route == "erplora"
    ticket()
    process()

    assert calls(gateway_answers) == [("erplora", "testing", False)]


# ── Going live fixes the route of that moment ────────────────────────────────────────────────────


def test_going_live_with_the_certificate_fixes_it_and_removing_it_never_falls_back_to_the_seal(
    issuer, opened, gateway_answers, switch
):
    upload_certificate()
    run("verifactu.config.go_live")
    assert Config.objects.get().route == Config.Route.OWN
    record = Record.objects.get(invoice_id=ticket().id)

    run("verifactu.certificate.remove")
    process()

    assert gateway_answers.calls == []
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == (Record.Status.PENDING, "own_certificate_missing")
    out = config()
    assert (out.route, out.issue_blocker.code) == ("own", "own_certificate_missing")
    assert refused_with_409(ticket) == "verifactu.own_certificate_missing"


def test_with_the_certificate_and_the_approved_authorisation_the_certificate_wins(issuer, opened, gateway_answers):
    upload_certificate()
    approve()

    assert run("verifactu.config.go_live").route == "own"
    assert Config.objects.get().route == Config.Route.OWN
    ticket()
    process()
    assert calls(gateway_answers) == [("own", "production", True)]


def test_on_without_a_certificate_the_approved_authorisation_goes_live_through_the_seal(issuer, opened):
    approve()

    assert run("verifactu.config.go_live").route == "erplora"
    assert Config.objects.get().route == Config.Route.ERPLORA


def test_on_without_a_certificate_nor_the_authorisation_it_does_not_go_live(issuer, opened):
    assert "representation_not_approved" in codes(config().live_blockers)

    assert refused_with_409(lambda: run("verifactu.config.go_live")) == "verifactu.representation_not_approved"
    assert config().environment == Environment.TESTING


def test_live_through_the_seal_a_new_certificate_changes_nothing(issuer, opened, gateway_answers):
    approve()
    run("verifactu.config.go_live")
    opened.VERIFACTU_ERPLORA_ROUTE_ENABLED = False
    upload_certificate()

    out = config()
    assert (out.route, out.route_ready_for_production, out.issue_blocker) == ("erplora", True, None)
    assert out.live_blockers == []
    alta = Record.objects.get(invoice_id=ticket().id)
    process()
    run("verifactu.record.cancel", {"record_id": str(alta.id), "reason": "Issued by error"})
    process()
    gateway_answers.set(aeat_holds())
    run("verifactu.aeat.query", {})

    assert calls(gateway_answers) == [("erplora", "production", False)] * 2
    assert calls(gateway_answers, gateway.QUERY_PATH) == [("erplora", "production", False)]
    assert Config.objects.get().route == Config.Route.ERPLORA


def test_live_removing_the_certificate_cures_nothing_so_a_refusal_stays_put(issuer, opened, gateway_answers):
    approve()
    run("verifactu.config.go_live")
    upload_certificate()
    gateway_answers.set(gateway.Reply(kind=gateway.REFUSED, code="verifactu_gateway.nif_mismatch", message="No."))
    record = Record.objects.get(invoice_id=ticket().id)
    process()

    run("verifactu.certificate.remove")
    process()

    assert calls(gateway_answers) == [("erplora", "production", False)]
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == (Record.Status.PENDING, "refused")


def test_live_through_the_seal_the_homes_step_stays_done_with_the_route_closed(issuer, opened):
    approve()
    run("verifactu.config.go_live")
    opened.VERIFACTU_ERPLORA_ROUTE_ENABLED = False

    out = config()
    assert out.route_ready_for_production is True
    assert "own_certificate_required" not in codes(out.live_blockers)


# ── ERPlora's own hub and the demos ──────────────────────────────────────────────────────────────


@pytest.fixture
def on_the_platform_hub(settings, in_business_b):
    """The whole test inside ERPlora's own hub, the business ``B``, with ERPlora's tax identity as its issuer."""
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.PLATFORM_ISSUER_TAX_ID = ISSUER["tax_id"]
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=PLATFORM))
        yield


def test_the_platform_hub_files_with_the_seal_even_with_a_certificate(on_the_platform_hub, gateway_answers, switch):
    gateway_answers.set(answering())
    upload_certificate(PLATFORM)

    assert config(PLATFORM).route == "erplora"
    ticket(PLATFORM)
    process(PLATFORM)

    assert calls(gateway_answers) == [("erplora", "testing", False)]


@pytest.fixture
def demo(hub_b, in_business_b):
    """``demo()``: inside a live demo with its issuer."""
    Hub.objects.filter(pk=hub_b.pk).update(is_demo=True, expires_at=timezone.now() + dt.timedelta(hours=1))
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=DEMO))
    return in_business_b


def test_a_demo_with_a_certificate_tests_with_it_and_without_one_with_the_seal(demo, gateway_answers, switch):
    gateway_answers.set(answering())
    with demo():
        ticket(DEMO)
        process(DEMO)
        upload_certificate(DEMO)
        ticket(DEMO)
        process(DEMO)

        assert calls(gateway_answers) == [("erplora", "testing", False), ("own", "testing", True)]
        assert config(DEMO).route == "own"
