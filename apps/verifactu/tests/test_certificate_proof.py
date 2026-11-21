"""The own certificate is proven by the AEAT's test environment (VERIFACTU-F02, F08): it is accepted once that AEAT
judges the records of a submission presented with it, and rejected when that AEAT refuses the certificate itself. A
business goes live with it only once it is accepted; uploading another one leaves it untested again.

How the AEAT's test door refuses a certificate was measured on ``prewww1.aeat.es``: one it cannot verify (no
recognised authority issued it, it is not valid for the service, or it has expired) is redirected, ``302`` with an
empty body, to its page «401 No autorizado. Se ha producido un error al verificar el certificado presentado». Its list
of errors names ``4112``: «El titular del certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o
Sucesor». The SOAP fault ``Codigo[103].NIF no identificado: <NIF>/<name>`` (the answer kept in ``fixtures/``, its
holder rewritten to the test's) is no verdict: the same door gave it to two good certificates and, a while later,
identified both, so it says nothing of the certificate.

The gateway is the only stand-in (``gateway_answers``): nothing here opens a connection."""

import pytest
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent

from apps.verifactu import aeat, certificates, gateway
from apps.verifactu.models import Event, OwnCertificate, Record, SendControl
from apps.verifactu.tests.conftest import FIXTURES, HUB_DB, answering, b64, codes, make_p12, run, ticket

pytestmark = HUB_DB

CERTIFICATE_REFUSED = gateway.Reply(kind=gateway.ANSWERED, aeat_status=302, aeat_body="")
HOLDER_NOT_IDENTIFIED_FOR_NOW = gateway.Reply(
    kind=gateway.ANSWERED,
    aeat_status=403,
    aeat_body=FIXTURES.joinpath("certificado_103_nif_no_identificado_2026-11-21.xml").read_text(encoding="utf-8"),
)


def fault(code: str, text: str, kind: str = "Client", status: int = 500) -> gateway.Reply:
    """A SOAP fault in the AEAT's own form (``Codigo[<code>].<text>``, as its door answers in ``fixtures/``)."""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?><env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<env:Body><env:Fault><faultcode>env:{kind}</faultcode><faultstring>Codigo[{code}].{text}</faultstring>"
        "</env:Fault></env:Body></env:Envelope>"
    )
    return gateway.Reply(kind=gateway.ANSWERED, aeat_status=status, aeat_body=body)


HOLDER_MAY_NOT_FILE = fault(
    "4112", "El titular del certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o Sucesor."
)


@pytest.fixture(autouse=True)
def storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = True


@pytest.fixture
def opened(settings, gateway_answers):
    """The prod deployment, opened by ERPlora: what going live needs from the server."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    return gateway_answers


def upload(p12: bytes | None = None):
    return run("verifactu.certificate.upload", {"p12_base64": b64(p12 or make_p12()), "password": "secret"})


def send_a_ticket(gateway_answers, reply) -> None:
    """A ticket goes out (in testing, by the own route) and the gateway answers ``reply``."""
    gateway_answers.set(reply)
    ticket()
    # As if the waits had passed: what an earlier answer left waiting goes out again in this pass.
    SendControl.objects.update(next_send_at=None)
    Record.objects.update(next_attempt_at=timezone.now())
    sent = len(gateway_answers.calls)
    run("verifactu.contingency.process")
    assert len(gateway_answers.calls) == sent + 1


def proof() -> tuple[str, str]:
    row = OwnCertificate.objects.get()
    return row.aeat_proof, row.aeat_proof_detail


def shown():
    return run("verifactu.config.get").own_certificate


# ── What an answer says of the certificate ───────────────────────────────────────────────────────


def test_an_answer_with_the_aeats_verdict_on_the_records_accepts_the_certificate():
    body = FIXTURES.joinpath("alta_2007_aceptado_con_errores_2026-08-02.xml").read_text(encoding="utf-8")
    assert aeat.certificate_verdict(200, body) == aeat.CertificateVerdict(accepted=True)


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (CERTIFICATE_REFUSED, ""),
        (HOLDER_MAY_NOT_FILE, "Codigo[4112].El titular del certificado debe ser Obligado Emisión"),
    ],
    ids=["302_cannot_verify", "4112_holder_may_not_file"],
)
def test_the_aeats_refusals_of_the_certificate_reject_it(reply, detail):
    verdict = aeat.certificate_verdict(reply.aeat_status, reply.aeat_body)
    assert verdict.accepted is False
    assert verdict.detail.startswith(detail)


@pytest.mark.parametrize(
    "reply",
    [
        fault("2000", "Servicio no disponible", kind="Server"),
        fault("4104", "Error en la cabecera: el valor del campo NIF del bloque ObligadoEmision no está identificado."),
        fault("4108", "Error técnico al obtener el certificado."),
        gateway.Reply(kind=gateway.ANSWERED, aeat_status=503, aeat_body="<html>maintenance</html>"),
        gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=""),
        HOLDER_NOT_IDENTIFIED_FOR_NOW,
    ],
    ids=["aeat_unavailable", "content_of_the_header", "technical", "maintenance_page", "empty", "103_for_now"],
)
def test_an_aeat_down_or_a_fault_of_the_content_says_nothing_of_the_certificate(reply):
    assert aeat.certificate_verdict(reply.aeat_status, reply.aeat_body) is None


# ── The certificate as the queue proves it ───────────────────────────────────────────────────────


def test_a_new_certificate_is_untested(issuer):
    upload()
    assert proof() == ("untested", "")
    assert (shown().aeat_proof, shown().aeat_proof_detail) == ("untested", "")


def test_the_aeat_of_testing_judging_its_records_proves_the_certificate(issuer, gateway_answers):
    upload()
    send_a_ticket(gateway_answers, answering())

    assert proof() == ("accepted", "")
    assert shown().aeat_proof == "accepted"
    [(path, payload)] = gateway_answers.calls
    # What proved it went to the AEAT's test environment: never to production.
    assert (path, payload["environment"], payload["route"]) == (gateway.SUBMIT_PATH, "testing", "own")
    assert Event.objects.filter(message_key="certificate_accepted_by_aeat").count() == 1


def test_a_record_the_aeat_rejects_for_its_content_still_proves_the_certificate(issuer, gateway_answers):
    upload()
    send_a_ticket(gateway_answers, answering("alta_3000_duplicado_tras_rechain_2026-08-02.xml"))
    assert proof() == ("accepted", "")


@pytest.mark.parametrize(
    ("reply", "detail", "said"),
    [
        (CERTIFICATE_REFUSED, "", "it could not verify it (no authority it recognises issued it"),
        (
            HOLDER_MAY_NOT_FILE,
            "Codigo[4112].El titular del certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o Sucesor.",
            "refused this certificate (Codigo[4112].El titular del certificado debe ser Obligado Emisión, Colaborador "
            "Social, Apoderado o Sucesor.): upload another one.",
        ),
    ],
    ids=["302_cannot_verify", "4112_holder_may_not_file"],
)
def test_the_aeat_of_testing_refusing_the_certificate_rejects_it(issuer, gateway_answers, reply, detail, said):
    upload()
    send_a_ticket(gateway_answers, reply)

    assert proof() == ("rejected", detail)
    out = shown()
    assert out.aeat_proof == "rejected"
    assert out.aeat_proof_detail.startswith("The AEAT's test environment refused this certificate")
    assert said in out.aeat_proof_detail
    assert Event.objects.filter(message_key="certificate_rejected_by_aeat", severity="warning").count() == 1


@pytest.mark.parametrize(
    "reply",
    [
        gateway.Reply(kind=gateway.UNREACHABLE, message="The gateway could not be reached."),
        gateway.Reply(kind=gateway.UNKNOWN, message="The request left and no answer came back."),
        gateway.Reply(kind=gateway.REFUSED, code="certificate_invalid", message="It does not open."),
        fault("2000", "Servicio no disponible", kind="Server"),
        fault("4104", "Error en la cabecera: el valor del campo NIF del bloque ObligadoEmision no está identificado."),
        HOLDER_NOT_IDENTIFIED_FOR_NOW,
    ],
    ids=["unreachable", "no_answer", "gateway_refusal", "aeat_unavailable", "content_fault", "103_for_now"],
)
def test_an_aeat_down_without_an_answer_or_a_content_error_leaves_it_untested(issuer, gateway_answers, reply):
    upload()
    send_a_ticket(gateway_answers, reply)
    assert proof() == ("untested", "")
    assert not Event.objects.filter(message_key__startswith="certificate_", message_key__endswith="_by_aeat").exists()


def test_an_aeat_down_after_it_was_accepted_keeps_it_accepted(issuer, gateway_answers):
    upload()
    send_a_ticket(gateway_answers, answering())
    send_a_ticket(gateway_answers, fault("2000", "Servicio no disponible", kind="Server"))
    assert proof() == ("accepted", "")


def test_a_rejected_certificate_the_aeat_accepts_later_is_accepted(issuer, gateway_answers):
    upload()
    send_a_ticket(gateway_answers, HOLDER_MAY_NOT_FILE)
    send_a_ticket(gateway_answers, answering())
    assert proof() == ("accepted", "")


def test_the_same_verdict_again_is_told_once(issuer, gateway_answers):
    upload()
    send_a_ticket(gateway_answers, CERTIFICATE_REFUSED)
    changes = OutboxEvent.objects.filter(name="verifactu.config.changed").count()
    send_a_ticket(gateway_answers, CERTIFICATE_REFUSED)
    assert Event.objects.filter(message_key="certificate_rejected_by_aeat").count() == 1
    assert OutboxEvent.objects.filter(name="verifactu.config.changed").count() == changes


@pytest.mark.parametrize("first", [answering(), CERTIFICATE_REFUSED], ids=["accepted", "rejected"])
def test_uploading_another_certificate_leaves_it_untested(issuer, gateway_answers, first):
    upload()
    send_a_ticket(gateway_answers, first)
    assert proof()[0] != "untested"

    upload(make_p12(days=200))

    assert proof() == ("untested", "")


def test_the_answer_for_a_certificate_replaced_meanwhile_does_not_prove_the_new_one(issuer, gateway_answers):
    upload()
    accepted = answering()

    def replaced_on_the_way(payload):
        OwnCertificate.objects.update(sealed_blob=certificates.seal(make_p12(days=200), "secret"))
        return accepted(payload)

    send_a_ticket(gateway_answers, replaced_on_the_way)
    assert proof() == ("untested", "")


def test_an_answer_of_production_never_proves_the_certificate(issuer, opened):
    upload()
    send_a_ticket(opened, answering())
    run("verifactu.config.go_live")
    upload(make_p12(days=200))

    send_a_ticket(opened, answering())

    assert opened.calls[-1][1]["environment"] == "production"
    assert proof() == ("untested", "")


# ── Going live ───────────────────────────────────────────────────────────────────────────────────


def go_live_refusal() -> str:
    with pytest.raises(Conflict) as refused:
        run("verifactu.config.go_live")
    return refused.value.code


@pytest.mark.parametrize(
    ("reply", "code"),
    [(None, "own_certificate_untested"), (CERTIFICATE_REFUSED, "own_certificate_rejected")],
    ids=["untested", "rejected"],
)
def test_it_cannot_go_live_with_a_certificate_not_accepted(issuer, opened, reply, code):
    upload()
    if reply is not None:
        send_a_ticket(opened, reply)

    config = run("verifactu.config.get")
    assert config.route_ready_for_production is False
    assert code in codes(config.live_blockers)
    assert go_live_refusal() == f"verifactu.{code}"
    assert run("verifactu.config.get").environment == "testing"


def test_it_goes_live_with_a_certificate_the_aeat_of_testing_accepted(issuer, opened):
    upload()
    send_a_ticket(opened, answering())

    config = run("verifactu.config.get")
    assert config.route_ready_for_production is True
    assert not codes(config.live_blockers) & {"own_certificate_untested", "own_certificate_rejected"}
    assert run("verifactu.config.go_live").environment == "production"


def test_a_business_already_live_keeps_filing_with_a_new_untested_certificate(issuer, opened):
    upload()
    send_a_ticket(opened, answering())
    run("verifactu.config.go_live")
    upload(make_p12(days=200))

    config = run("verifactu.config.get")
    assert config.issue_blocker is None
    assert config.route_ready_for_production is True
    not_proven = {"own_certificate_untested", "own_certificate_rejected"}
    assert not (codes(config.reasons) | codes(config.live_blockers)) & not_proven
