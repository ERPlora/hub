"""The own certificate is kept whatever authority issued it (VERIFACTU-F02, F04): the Hub keeps no list of
authorities, and whether the AEAT takes it is for the AEAT's test environment to say (``test_certificate_proof``).

Every .p12 is made by the test. Nothing here opens a connection: no AEAT, of testing or of production."""

import socket

import pytest

from apps.verifactu import certificates
from apps.verifactu.models import OwnCertificate
from apps.verifactu.queries.route import production_open
from apps.verifactu.tests.conftest import HUB_DB, b64, codes, make_p12, run

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()


@pytest.fixture(autouse=True)
def no_connection(monkeypatch):
    """Whatever tried to reach a server from here (the gateway, the AEAT) would fail the test."""

    def refuse(self, address):
        raise AssertionError(f"checking a certificate opened a connection to {address}")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_these_tests_can_never_file_in_production():
    assert not production_open()


def test_upload_keeps_a_certificate_whatever_authority_issued_it(issuer):
    # ``TEST_AUTHORITY`` is made up by the test: no list of recognised authorities names it.
    config = run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"})
    assert (config.route, config.own_certificate.loaded) == ("own", True)
    row = OwnCertificate.objects.get()
    assert (row.holder_tax_id, row.aeat_proof) == ("B12345674", OwnCertificate.Proof.UNTESTED)
    assert not config.route_ready_for_production
    assert "own_certificate_untested" in codes(config.live_blockers)
