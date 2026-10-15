"""The business's own certificate (VERIFACTU-F02, F03): read, checked and kept sealed in the hub's database.

What is read follows the SaaS's gateway (``fiscal_gateway/seal.py``), which presents with it: the holder is the
subject's ``organizationIdentifier`` and else its ``serialNumber``, without the ETSI prefix; a declared Extended
Key Usage without client authentication can never open the AEAT's mTLS connection and is refused. The .p12 and
its password are kept together, encrypted with Fernet under ``FISCAL_CERTIFICATE_KEY``: without the key nothing
is kept, and a rotated key cannot open what the old one sealed. Every .p12 here is made by the test.
"""

import datetime as dt

import pytest

from apps.verifactu import certificates, gateway
from apps.verifactu.tests.conftest import b64, make_p12


def test_inspect_reads_the_holder_from_organization_identifier_first():
    facts = certificates.inspect(make_p12(), "secret")
    assert facts.holder_tax_id == "B12345674"
    assert facts.holder == "ACME SL"
    assert facts.expires_at > dt.datetime.now(dt.UTC)


def test_inspect_falls_back_to_serial_number():
    facts = certificates.inspect(
        make_p12(org_id=None, serial="IDCES-12345678Z"), "secret"
    )
    assert facts.holder_tax_id == "12345678Z"


def test_the_kind_is_read_as_the_gateway_reads_it():
    assert certificates.inspect(make_p12(), "secret").kind == "representative"
    assert certificates.inspect(make_p12(org_id=None), "secret").kind == "personal"
    assert certificates.inspect(make_p12(serial=None), "secret").kind == "unknown"
    assert certificates.inspect(make_p12(eseal=True), "secret").kind == "seal"


def test_a_certificate_without_extended_key_usage_may_authenticate():
    assert (
        certificates.inspect(make_p12(client_auth=None), "secret").holder_tax_id
        == "B12345674"
    )


def test_a_declared_eku_without_client_auth_is_refused():
    with pytest.raises(certificates.CertificateInvalid):
        certificates.inspect(make_p12(client_auth=False), "secret")


def test_a_wrong_password_is_refused():
    with pytest.raises(certificates.CertificateInvalid):
        certificates.inspect(make_p12(), "nope")


def test_what_is_not_a_p12_is_refused():
    with pytest.raises(certificates.CertificateInvalid):
        certificates.inspect(b"not a certificate", "secret")


def test_the_refusal_never_carries_the_password():
    with pytest.raises(certificates.CertificateInvalid) as refused:
        certificates.inspect(make_p12(password=b"hunter2-secret"), "hunter2-wrong")
    assert "hunter2" not in str(refused.value)


def test_seal_and_open_round_trip(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    p12 = make_p12()
    blob = certificates.seal(p12, "secret")
    assert blob != p12 and b"secret" not in blob
    assert certificates.open(blob) == (p12, "secret")


def test_without_a_key_storage_is_unavailable(settings):
    settings.FISCAL_CERTIFICATE_KEY = ""
    assert certificates.storage_available() is False
    with pytest.raises(certificates.StorageUnavailable):
        certificates.seal(b"x", "y")


def test_a_key_that_is_not_a_fernet_key_is_no_storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = "not-a-key"
    assert certificates.storage_available() is False
    with pytest.raises(certificates.StorageUnavailable):
        certificates.seal(b"x", "y")


def test_a_rotated_key_cannot_open_the_blob(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    blob = certificates.seal(make_p12(), "secret")
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    with pytest.raises(certificates.CertificateUnreadable):
        certificates.open(blob)


def test_without_a_key_the_blob_is_unreadable(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    blob = certificates.seal(make_p12(), "secret")
    settings.FISCAL_CERTIFICATE_KEY = ""
    with pytest.raises(certificates.CertificateUnreadable):
        certificates.open(blob)


def test_the_material_is_what_the_gateway_takes(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    p12 = make_p12()
    material = certificates.material(certificates.seal(p12, "secret"))
    assert material == gateway.Certificate(p12_base64=b64(p12), password="secret")
    assert "secret" not in repr(material)
