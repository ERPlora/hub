"""The own certificate is checked against the trusted list of recognised authorities (VERIFACTU-F02, F04): when it is
uploaded, and again, by the scheduled task, once it is kept. One that no recognised authority issued never counts: the
screen shows no certificate and asks for one, and the records go by the route they would take without it.

Every .p12 is made by the test. Nothing here opens a connection: no AEAT, of testing or of production."""

import datetime as dt
import socket

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent

from apps.verifactu import certificates, trust
from apps.verifactu.models import Event, OwnCertificate, Record
from apps.verifactu.queries.route import certificate_valid, production_open
from apps.verifactu.tests.conftest import HUB_DB, A, b64, make_p12, manual, run

pytestmark = HUB_DB

ISSUER_NIF = "B12345674"
RECHECK = "verifactu.certificate.recheck"


@pytest.fixture(autouse=True)
def storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()


@pytest.fixture(autouse=True)
def no_connection(monkeypatch):
    """Whatever tried to reach a server from here (the gateway, the AEAT) would fail the test."""

    def refuse(self, address):
        raise AssertionError(f"checking a certificate opened a connection to {address}")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def upload(p12: bytes):
    return run(
        "verifactu.certificate.upload", {"p12_base64": b64(p12), "password": "secret"}
    )


def recheck():
    """The scheduled task's run: as the system, as the worker runs it."""
    return run(RECHECK, ctx=system_context(A))


def kept_before_the_check(p12: bytes) -> OwnCertificate:
    """A certificate as an upload left it before uploads were checked against the trusted list."""
    return OwnCertificate.objects.create(
        holder="ACME SL",
        holder_tax_id=ISSUER_NIF,
        kind="representative",
        expires_at=timezone.now() + dt.timedelta(days=300),
        sealed_blob=certificates.seal(p12, "secret"),
        uploaded_by="ana",
    )


def test_these_tests_can_never_file_in_production():
    assert not production_open()


def test_upload_refuses_a_certificate_no_recognised_authority_issued(issuer):
    with pytest.raises(Conflict) as refused:
        upload(make_p12(unrecognised=True))
    assert refused.value.code == "verifactu.certificate_invalid"
    assert "FNMT" in str(refused.value)
    assert not OwnCertificate.objects.exists()
    config = run("verifactu.config.get")
    assert (config.route, config.own_certificate.loaded) == ("erplora", False)


def test_an_uploaded_certificate_keeps_the_list_it_was_checked_against(issuer):
    upload(make_p12())
    row = OwnCertificate.objects.get()
    assert (row.issuer_recognised, row.checked_list) == (True, trust.sequence())


@pytest.mark.parametrize("made", [{"self_signed": True}, {"unrecognised": True}], ids=["self_signed", "unrecognised"])
def test_a_kept_certificate_no_recognised_authority_issued_stops_counting(issuer, made):
    kept_before_the_check(make_p12(**made))
    assert run("verifactu.config.get").route == "own"
    config = recheck()
    assert (config.route, config.own_certificate.loaded) == ("erplora", False)
    assert not config.route_ready_for_production
    assert not certificate_valid()
    row = OwnCertificate.objects.get()
    assert (row.issuer_recognised, row.checked_list) == (False, trust.sequence())
    refused = Event.objects.get(message_key="certificate_refused")
    assert (refused.severity, refused.params["holder_tax_id"]) == ("warning", ISSUER_NIF)
    assert OutboxEvent.objects.filter(name="verifactu.config.changed").exists()


def sealed_record() -> Record:
    invoice = manual(series_code="TICKET")
    return Record.objects.get(pk=run("verifactu.record.create", {"invoice_id": str(invoice.id)}).record.id)


def test_the_refusal_sends_again_what_the_gateway_refused_and_leaves_what_the_aeat_has(issuer):
    # Like a removal: the testing record the gateway refused with that certificate goes out with the next pass, by
    # ERPlora's seal. A record the AEAT already has is never touched, whatever it says.
    waiting, in_aeat = sealed_record(), sealed_record()
    long_ago = timezone.now() - dt.timedelta(days=30)
    refusal = {"wait_reason": "refused", "wait_detail": "Not the declared NIF.", "next_attempt_at": long_ago}
    Record.objects.filter(pk=waiting.id).update(**refusal)
    Record.objects.filter(pk=in_aeat.id).update(status="accepted", **refusal)
    kept_before_the_check(make_p12(unrecognised=True))
    recheck()
    waiting.refresh_from_db()
    in_aeat.refresh_from_db()
    assert (waiting.wait_reason, waiting.wait_detail) == ("", "")
    assert waiting.next_attempt_at > long_ago
    assert (in_aeat.status, in_aeat.wait_reason, in_aeat.wait_detail, in_aeat.next_attempt_at) == (
        "accepted",
        "refused",
        "Not the declared NIF.",
        long_ago,
    )


def test_a_kept_certificate_a_recognised_authority_issued_keeps_counting(issuer):
    kept_before_the_check(make_p12())
    config = recheck()
    assert (config.route, config.own_certificate.loaded) == ("own", True)
    row = OwnCertificate.objects.get()
    assert (row.issuer_recognised, row.checked_list) == (True, trust.sequence())
    assert not Event.objects.filter(message_key="certificate_refused").exists()


def test_a_kept_certificate_this_server_cannot_open_is_left_unchecked(issuer, settings):
    kept_before_the_check(make_p12(unrecognised=True))
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    recheck()
    row = OwnCertificate.objects.get()
    assert (row.issuer_recognised, row.checked_list) == (None, None)
    assert not Event.objects.filter(message_key="certificate_refused").exists()


def test_a_new_trusted_list_checks_the_kept_certificate_again(issuer, monkeypatch):
    upload(make_p12())
    monkeypatch.setattr(trust, "sequence", lambda: 10_000)
    monkeypatch.setattr(trust, "authorities", lambda: ())
    config = recheck()
    assert (config.route, config.own_certificate.loaded) == ("erplora", False)
    assert OwnCertificate.objects.get().checked_list == 10_000


def test_a_certificate_checked_against_this_list_is_not_checked_again(issuer, monkeypatch):
    upload(make_p12())

    def never(p12, password):
        raise AssertionError("a certificate already checked against this list was checked again")

    monkeypatch.setattr(certificates, "inspect", never)
    assert recheck().own_certificate.loaded


def test_uploading_a_valid_certificate_after_a_refusal_counts_again(issuer):
    kept_before_the_check(make_p12(self_signed=True))
    recheck()
    config = upload(make_p12())
    assert (config.route, config.own_certificate.loaded) == ("own", True)
    assert OwnCertificate.objects.get().issuer_recognised is True


def test_only_the_platform_checks_a_kept_certificate(issuer):
    kept_before_the_check(make_p12(self_signed=True))
    with pytest.raises(PermissionDenied):
        run(RECHECK)
    assert OwnCertificate.objects.get().issuer_recognised is None

