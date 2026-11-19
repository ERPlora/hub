"""Spain's trusted list read into the list the app keeps (``manage.py verifactu_trusted_list``): the issuing CAs of
qualified certificates for electronic signatures or seals, still in force, each with its withdrawal if it has one.
The lists here are written by the test in the ETSI TS 119 612 layout the Ministry publishes; none is downloaded."""

import base64
import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.verifactu import trusted_list

CA_QC = "http://uri.etsi.org/TrstSvc/Svctype/CA/QC"
TSA = "http://uri.etsi.org/TrstSvc/Svctype/TSA/QTST"
SIGNATURES = "ForeSignatures"
SEALS = "ForeSeals"
WEBSITES = "ForWebSiteAuthentication"


def ca(common_name: str, *, expires_in_days: int = 3650) -> x509.Certificate:
    signer = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(signer.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=4000))
        .not_valid_after(now + dt.timedelta(days=expires_in_days))
        .sign(signer, hashes.SHA256())
    )


def der64(certificate: x509.Certificate) -> str:
    return base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()


def service(
    certificate: x509.Certificate,
    *,
    kind: str = CA_QC,
    status: str = "granted",
    since: str = "2016-07-01T00:00:00Z",
    uses: tuple[str, ...] = (SIGNATURES,),
    title: str = "Qualified certificates issued by Test CA",
) -> str:
    qualifiers = "".join(
        "<Extension Critical='false'><AdditionalServiceInformation>"
        f"<URI xml:lang='en'>http://uri.etsi.org/TrstSvc/TrustedList/SvcInfoExt/{use}</URI>"
        "</AdditionalServiceInformation></Extension>"
        for use in uses
    )
    return (
        "<TSPService><ServiceInformation>"
        f"<ServiceTypeIdentifier>{kind}</ServiceTypeIdentifier>"
        f"<ServiceName><Name xml:lang='es'>Certificados de prueba</Name><Name xml:lang='en'>{title}</Name></ServiceName>"
        "<ServiceDigitalIdentity><DigitalId><X509Certificate>\n"
        f"{der64(certificate)}\n"
        "</X509Certificate></DigitalId></ServiceDigitalIdentity>"
        f"<ServiceStatus>http://uri.etsi.org/TrstSvc/TrustedList/Svcstatus/{status}</ServiceStatus>"
        f"<StatusStartingTime>{since}</StatusStartingTime>"
        f"<ServiceInformationExtensions>{qualifiers}</ServiceInformationExtensions>"
        "</ServiceInformation></TSPService>"
    )


def tsl(*services: str, territory: str = "ES", sequence: int = 191) -> bytes:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<TrustServiceStatusList xmlns='http://uri.etsi.org/02231/v2#'><SchemeInformation>"
        f"<TSLSequenceNumber>{sequence}</TSLSequenceNumber>"
        "<TSLType>http://uri.etsi.org/TrstSvc/TrustedList/TSLType/EUgeneric</TSLType>"
        f"<SchemeTerritory>{territory}</SchemeTerritory>"
        "<ListIssueDateTime>2026-11-04T02:00:00Z</ListIssueDateTime>"
        "<NextUpdate><dateTime>2027-04-26T01:00:00Z</dateTime></NextUpdate>"
        "<PointersToOtherTSL><OtherTSLPointer><AdditionalInformation>"
        "<SchemeTerritory>EU</SchemeTerritory></AdditionalInformation></OtherTSLPointer></PointersToOtherTSL>"
        "</SchemeInformation><TrustServiceProviderList><TrustServiceProvider>"
        "<TSPInformation><TSPName><Name xml:lang='es'>Prestador de prueba</Name></TSPName></TSPInformation>"
        f"<TSPServices>{''.join(services)}</TSPServices>"
        "</TrustServiceProvider></TrustServiceProviderList></TrustServiceStatusList>"
    ).encode()


def kept(xml: bytes) -> list[dict]:
    return trusted_list.read(xml, dt.datetime.now(dt.UTC))["authorities"]


def test_an_authority_for_signatures_or_seals_is_kept_with_its_provider_and_service():
    signatures, seals = ca("Signatures CA"), ca("Seals CA")
    authorities = kept(tsl(service(signatures), service(seals, uses=(SEALS,), title="Seals")))
    assert {entry["certificate"] for entry in authorities} == {der64(signatures), der64(seals)}
    assert {(entry["provider"], entry["withdrawn_at"]) for entry in authorities} == {("Prestador de prueba", None)}
    assert "Qualified certificates issued by Test CA" in {entry["service"] for entry in authorities}


def test_an_authority_only_for_websites_is_left_out():
    assert kept(tsl(service(ca("Web CA"), uses=(WEBSITES,)))) == []


def test_what_is_not_an_authority_of_qualified_certificates_is_left_out():
    assert kept(tsl(service(ca("Time stamps"), kind=TSA))) == []


def test_a_withdrawn_authority_is_kept_with_the_moment_it_stopped_being_qualified():
    (entry,) = kept(tsl(service(ca("Old CA"), status="withdrawn", since="2025-10-30T02:00:00Z")))
    assert entry["withdrawn_at"] == "2025-10-30T02:00:00+00:00"


def test_an_authority_whose_certificate_expired_is_left_out():
    assert kept(tsl(service(ca("Expired CA", expires_in_days=-1)))) == []


def test_an_authority_listed_twice_is_kept_once_as_still_qualified():
    twice = ca("Twice CA")
    (entry,) = kept(tsl(service(twice, status="withdrawn", since="2024-01-01T00:00:00Z"), service(twice)))
    assert entry["withdrawn_at"] is None


def test_the_list_says_which_one_it_is():
    read = trusted_list.read(tsl(service(ca("Any CA")), sequence=191), dt.datetime.now(dt.UTC))
    assert (read["source"], read["sequence"]) == (trusted_list.TSL_URL, 191)
    assert (read["issued_at"], read["next_update"]) == ("2026-11-04T02:00:00Z", "2027-04-26T01:00:00Z")


def test_another_countrys_list_is_refused():
    with pytest.raises(trusted_list.TrustedListInvalid):
        trusted_list.read(tsl(service(ca("Any CA")), territory="PT"), dt.datetime.now(dt.UTC))


def test_what_is_not_a_trusted_list_is_refused():
    with pytest.raises(trusted_list.TrustedListInvalid):
        trusted_list.read(b"<html>Not found</html>", dt.datetime.now(dt.UTC))
    with pytest.raises(trusted_list.TrustedListInvalid):
        trusted_list.read(b"not xml", dt.datetime.now(dt.UTC))
