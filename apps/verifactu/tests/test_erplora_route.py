"""ERPlora's route, where ERPlora files on a business's behalf with its own seal, closes to newcomers with a deployment
switch (``VERIFACTU_ERPLORA_ROUTE_ENABLED``), on by default.

Off, a business can neither choose it, nor ask for or send the signed authorisation, nor go live through it: only its
own certificate takes it to production, and the Home's step asks for that. Testing still files with the seal, demos
included, and a business already live through it keeps sending and cancelling, since the AEAT only takes a
cancellation presented with the seal that filed the record. ERPlora's own hub (the business ``B`` here) behaves as
with the switch on.
"""

import base64
import datetime as dt
import json

import httpx
import pytest
import respx
from django.utils import timezone, translation
from live.context import system_context
from live.errors import Conflict, OperationError

from apps.verifactu import certificates
from apps.verifactu.models import Config, Environment, Record, SendControl
from apps.verifactu.tests.conftest import (
    HOST,
    HUB_DB,
    ISSUER,
    A,
    B,
    answering,
    b64,
    ctx_for,
    make_p12,
    run,
)
from base.models import Hub

pytestmark = HUB_DB

SAAS = "http://saas.internal:8001"
MODEL_URL = f"{SAAS}/internal/representation/model"
PDF = base64.b64encode(b"%PDF-1.7 signed").decode()
SUBMISSION = {
    "signer_tax_id": "12345678Z",
    "signer_name": "Ana Pérez",
    "signer_document_type": "dni",
    "signed_model_base64": PDF,
    "id_copy_base64": PDF,
    "representation_proof_base64": PDF,
}
CLOSED_ES = "de momento ERPlora no presenta por cuenta de los negocios: usa tu propio certificado"
PLATFORM = B
DEMO = B


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway and the key that keeps the own certificates."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = SAAS
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


@pytest.fixture(autouse=True)
def switched_on(settings):
    """On unless a test turns it off, whatever the environment of the run says; the key that keeps the own
    certificates set."""
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = True
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


@pytest.fixture
def switched_off(switched_on):
    switched_on.VERIFACTU_ERPLORA_ROUTE_ENABLED = False
    return switched_on


@pytest.fixture
def saas(settings):
    settings.SAAS_INTERNAL_URL = SAAS
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith=MODEL_URL).mock(return_value=httpx.Response(200, content=b"%PDF-1.4 Anexo I"))
        mock.post(url__startswith=f"{SAAS}/internal/hubs/").mock(return_value=httpx.Response(404))
        yield mock


def code_of(call) -> str:
    with pytest.raises(OperationError) as refused:
        call()
    return refused.value.code


def refused_with_409(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    assert refused.value.status == 409
    return refused.value.code


def approve(scope=A, version: int = 1) -> None:
    run(
        "verifactu.config.sync",
        {"version": version, "representation": {"status": "approved"}},
        system_context(scope),
    )


def own_certificate(scope=A) -> None:
    ctx = ctx_for(scope=scope)
    run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"}, ctx)
    run("verifactu.config.update", {"route": "own"}, ctx)


def config(scope=A, language: str = "en"):
    return run("verifactu.config.get", ctx=ctx_for(scope=scope, language=language))


def codes(waits) -> set[str]:
    return {wait.code for wait in waits}


def ticket(scope=A):
    lines = [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]
    return run("invoice.invoice.create", {"lines": lines, "series_code": "TICKET"}, ctx_for(scope=scope))


def sent(gateway_answers) -> list[tuple[str, str]]:
    return [(payload["route"], payload["environment"]) for _path, payload in gateway_answers.calls]


# ── On, as ever ─────────────────────────────────────────────────────────────────────────────────


def test_on_the_route_is_offered(issuer):
    assert config().erplora_route_available is True


def test_on_a_business_goes_live_through_erplora_with_its_approved_authorisation(issuer, opened):
    approve()
    assert config().route_ready_for_production is True
    assert config().live_blockers == []

    assert run("verifactu.config.go_live").environment == Environment.PRODUCTION


def test_on_a_business_chooses_erplora_and_reaches_the_authorisation(issuer, saas):
    own_certificate()

    assert run("verifactu.config.update", {"route": "erplora"}).route == "erplora"
    assert run("verifactu.representation.model").content_type == "application/pdf"
    # The switch lets it through: what stops it now is the SaaS not knowing this business yet.
    assert code_of(lambda: run("verifactu.representation.submit", SUBMISSION)) == "verifactu.hub_unregistered"


# ── Off, for a business ─────────────────────────────────────────────────────────────────────────


def test_off_the_route_is_not_offered(issuer, switched_off):
    assert config().erplora_route_available is False


@pytest.mark.parametrize("authorisation", ["none", "approved"])
def test_off_going_live_through_erplora_asks_for_the_own_certificate(issuer, opened, switched_off, authorisation):
    if authorisation == "approved":
        approve()

    assert refused_with_409(lambda: run("verifactu.config.go_live")) == "verifactu.own_certificate_required"
    assert config().environment == Environment.TESTING


def test_off_the_own_certificate_still_goes_live(issuer, opened, switched_off):
    own_certificate()

    assert run("verifactu.config.go_live").environment == Environment.PRODUCTION


def test_off_settings_say_the_own_certificate_is_what_is_missing_to_go_live(issuer, opened, switched_off):
    approve()

    assert codes(config().live_blockers) == {"own_certificate_required"}
    with translation.override("es"):
        (blocker,) = config(language="es").live_blockers
    assert blocker.message == CLOSED_ES
    own_certificate()
    assert config().live_blockers == []


def test_off_the_homes_step_is_done_only_with_the_own_certificate(issuer, switched_off):
    approve()
    assert config().route_ready_for_production is False

    own_certificate()
    assert config().route_ready_for_production is True


def test_off_choosing_erplora_is_a_409_and_the_route_stays(issuer, switched_off):
    own_certificate()

    refusal = refused_with_409(lambda: run("verifactu.config.update", {"route": "erplora"}))

    assert refusal == "verifactu.erplora_route_unavailable"
    assert Config.objects.get().route == Config.Route.OWN
    # Choosing the own route, or keeping ERPlora's where it already is, changes nothing new.
    assert run("verifactu.config.update", {"route": "own"}).route == "own"


def test_off_a_business_already_on_erplora_may_keep_it(issuer, switched_off):
    assert config().route == "erplora"

    assert run("verifactu.config.update", {"route": "erplora"}).route == "erplora"


def test_off_choosing_erplora_over_http_is_a_409_said_in_spanish(client, make_user, issuer, switched_off):
    own_certificate()
    client.force_login(make_user("boss", host=A.key, role="hub_admin"))

    response = client.post(
        "/api/verifactu/config",
        json.dumps({"route": "erplora"}),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE="es",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verifactu.erplora_route_unavailable"
    assert response.json()["error"]["message"] == (
        "De momento ERPlora no presenta por cuenta de los negocios: presenta con tu propio certificado."
    )


def test_off_the_authorisation_can_be_neither_asked_for_nor_sent(issuer, switched_off, saas):
    asked = refused_with_409(lambda: run("verifactu.representation.model"))
    sent_it = refused_with_409(lambda: run("verifactu.representation.submit", SUBMISSION))

    assert (asked, sent_it) == ("verifactu.erplora_route_unavailable", "verifactu.erplora_route_unavailable")
    assert saas.calls.call_count == 0
    assert config().representation.status == Config.Representation.NONE


# ── Off, for those already filing with the seal ────────────────────────────────────────────────


def test_off_testing_still_files_with_the_seal(issuer, switched_off, gateway_answers):
    gateway_answers.set(answering())
    record = Record.objects.get(invoice_id=ticket().id)

    run("verifactu.contingency.process")

    assert sent(gateway_answers) == [("erplora", "testing")]
    record.refresh_from_db()
    assert record.status == "accepted"


@pytest.fixture
def demo(hub_b, in_business_b):
    """``demo()``: inside a live demo with its issuer, on ERPlora's route as every demo is."""
    Hub.objects.filter(pk=hub_b.pk).update(is_demo=True, expires_at=timezone.now() + dt.timedelta(hours=1))
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=DEMO))
    return in_business_b


def test_off_a_demo_still_files_with_the_seal_in_testing(demo, switched_off, gateway_answers):
    gateway_answers.set(answering())
    with demo():
        ticket(DEMO)
        run("verifactu.contingency.process", ctx=ctx_for(scope=DEMO))

        assert sent(gateway_answers) == [("erplora", "testing")]
        assert Record.objects.get().status == "accepted"


def test_off_a_business_live_through_erplora_keeps_issuing_sending_and_cancelling(
    issuer, opened, gateway_answers
):
    approve()
    run("verifactu.config.go_live")
    opened.VERIFACTU_ERPLORA_ROUTE_ENABLED = False
    gateway_answers.set(answering())

    alta = Record.objects.get(invoice_id=ticket().id)
    run("verifactu.contingency.process")
    cancellation = run("verifactu.record.cancel", {"record_id": str(alta.id), "reason": "Issued by error"}).record
    SendControl.objects.update(next_send_at=timezone.now() - dt.timedelta(seconds=1))
    run("verifactu.contingency.process")

    assert sent(gateway_answers) == [("erplora", "production"), ("erplora", "production")]
    assert Record.objects.get(pk=alta.id).status == "accepted"
    assert Record.objects.get(pk=cancellation.id).status == "accepted"
    assert config().issue_blocker is None


# ── ERPlora's own hub ───────────────────────────────────────────────────────────────────────────


@pytest.fixture
def on_the_platform_hub(settings, in_business_b):
    """The whole test inside ERPlora's own hub, the business ``B``, with ERPlora's tax identity as its issuer."""
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.PLATFORM_ISSUER_TAX_ID = ISSUER["tax_id"]
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=PLATFORM))
        yield


@pytest.mark.parametrize("enabled", [True, False])
def test_the_platform_hub_ignores_the_switch(on_the_platform_hub, settings, saas, enabled):
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = enabled
    ctx = ctx_for(scope=PLATFORM)
    own_certificate(PLATFORM)

    assert run("verifactu.config.update", {"route": "erplora"}, ctx).route == "erplora"
    out = config(PLATFORM)
    assert (out.erplora_route_available, out.route_ready_for_production) == (True, True)
    assert "own_certificate_required" not in codes(out.live_blockers)
    assert run("verifactu.representation.model", ctx=ctx).content_type == "application/pdf"
    assert code_of(lambda: run("verifactu.representation.submit", SUBMISSION, ctx)) == "verifactu.hub_unregistered"
    assert code_of(lambda: run("verifactu.config.go_live", ctx=ctx)) == "verifactu.platform_fixed"
