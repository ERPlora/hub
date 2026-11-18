"""Which authorities the AEAT recognises (VERIFACTU-F02): the issuing CAs of qualified certificates for electronic
signatures and seals in Spain's trusted list, kept in the app. A certificate counts when one of them signed it while
it was qualified; a name alone proves nothing. Every certificate here is made by the test."""

import base64
import datetime as dt
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.verifactu import trust

def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def key():
    return ec.generate_private_key(ec.SECP256R1())


def name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def authority(subject: x509.Name, signer) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(signer.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now() - dt.timedelta(days=3650))
        .not_valid_after(now() + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(signer, hashes.SHA256())
    )


def issued(issuer: x509.Name, signer, *, days_ago: int = 1) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(name("ACME SL"))
        .issuer_name(issuer)
        .public_key(key().public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now() - dt.timedelta(days=days_ago))
        .not_valid_after(now() + dt.timedelta(days=365))
        .sign(signer, hashes.SHA256())
    )


def listing(monkeypatch, *authorities: trust.Authority) -> None:
    monkeypatch.setattr(trust, "authorities", lambda: authorities)


def test_a_certificate_a_listed_authority_issued_is_recognised(monkeypatch):
    signer = key()
    ca = authority(name("Listed CA"), signer)
    listing(monkeypatch, trust.Authority(ca))
    assert trust.recognised(issued(ca.subject, signer))


def test_an_authority_under_a_listed_name_but_with_another_key_is_not(monkeypatch):
    ca = authority(name("Listed CA"), key())
    listing(monkeypatch, trust.Authority(ca))
    assert not trust.recognised(issued(ca.subject, key()))


def test_an_authority_the_list_does_not_name_is_not(monkeypatch):
    listing(monkeypatch, trust.Authority(authority(name("Listed CA"), key())))
    signer = key()
    other = authority(name("Unlisted CA"), signer)
    assert not trust.recognised(issued(other.subject, signer))


def test_with_no_authority_listed_nothing_is_recognised(monkeypatch):
    listing(monkeypatch)
    signer = key()
    assert not trust.recognised(issued(name("Any CA"), signer))


def test_a_withdrawn_authority_still_vouches_for_what_it_issued_before(monkeypatch):
    signer = key()
    ca = authority(name("Withdrawn CA"), signer)
    listing(monkeypatch, trust.Authority(ca, withdrawn_at=now() - dt.timedelta(days=30)))
    assert trust.recognised(issued(ca.subject, signer, days_ago=60))
    assert not trust.recognised(issued(ca.subject, signer, days_ago=10))


def test_one_listing_of_an_authority_still_qualified_is_enough(monkeypatch):
    signer = key()
    ca = authority(name("Relisted CA"), signer)
    listing(monkeypatch, trust.Authority(ca, withdrawn_at=now() - dt.timedelta(days=30)), trust.Authority(ca))
    assert trust.recognised(issued(ca.subject, signer, days_ago=10))


def kept_entries() -> list[dict]:
    return json.loads(trust.LIST_FILE.read_text())["authorities"]


def test_the_kept_list_is_spains_with_the_fnmts_authorities():
    kept = trust.kept()
    assert kept.sequence == json.loads(trust.LIST_FILE.read_text())["sequence"] > 0
    assert len(kept.authorities) == len(kept_entries())
    services = {entry["service"] for entry in kept_entries()}
    assert any("AC FNMT Usuarios" in service for service in services)
    assert any("AC Representación" in service for service in services)


def test_a_real_authoritys_name_without_its_key_is_not_recognised(monkeypatch):
    listing(monkeypatch, *trust.kept().authorities)
    (fnmt,) = [
        x509.load_der_x509_certificate(base64.b64decode(entry["certificate"]))
        for entry in kept_entries()
        if "AC FNMT Usuarios" in entry["service"] and entry["withdrawn_at"] is None
    ]
    assert not trust.recognised(issued(fnmt.subject, key()))
