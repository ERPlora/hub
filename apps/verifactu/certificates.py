"""The business's own certificate (VERIFACTU-F02, F03): what it says, and how it is kept in the hub's database.

``inspect`` opens a .p12 with its password and reads what the Hub shows and checks, with the semantics of the
SaaS's gateway that presents with it (``fiscal_gateway/seal.py``):

- ``holder_tax_id``: the subject's ``organizationIdentifier`` first, its ``serialNumber`` after, without the ETSI
  EN 319 412-1 prefix (``VATES-B12345674`` → ``B12345674``, ``IDCES-12345678Z`` → ``12345678Z``);
- ``kind``: ``seal`` only with the eIDAS QcType eSeal (``0.4.0.1862.1.6.2``) and not eSign; else
  ``representative`` (an entity and a person's DNI/NIE), ``personal`` (a person only) or ``unknown``;
- a declared Extended Key Usage without clientAuth (nor anyExtendedKeyUsage) can never open the AEAT's mTLS
  connection: ``CertificateInvalid``, as a password that does not open it.

``seal`` keeps the .p12 and its password together, encrypted with Fernet (AES-128-CBC + HMAC-SHA256, from
``cryptography``) under ``settings.FISCAL_CERTIFICATE_KEY``; ``open`` gives them back, or ``CertificateUnreadable``
when the key is missing or is not the one that sealed them (rotated). Nothing here touches the database: the
row (``OwnCertificate``) is read and written by ``queries.py`` and ``services.py``. Nothing of the certificate
(the .p12, its password, its key) reaches a message, a log or a traceback: errors name what failed only.
"""

import base64
import binascii
import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Literal

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.conf import settings

from apps.verifactu import gateway

Kind = Literal["seal", "representative", "personal", "unknown"]

# eIDAS QcType eSeal and eSign (0.4.0.1862.1.6.2 and .1), DER-encoded as they appear inside the qcStatements
# extension: found by their bytes, as the gateway does, because the library has no parser for qcStatements.
_QC_TYPE_ESEAL = bytes.fromhex("060704008e46010602")
_QC_TYPE_ESIGN = bytes.fromhex("060704008e46010601")
# The ETSI EN 319 412-1 semantics prefix of an identifier: type (VAT, IDC, NTR…), country, hyphen.
_ETSI_PREFIX = re.compile(r"^[A-Z]{3}[A-Z]{2}-")
# A Spanish DNI (8 digits and a letter) or NIE (X/Y/Z, 7 digits and a letter): a natural person.
_PERSON_ID = re.compile(r"^(\d{8}|[XYZ]\d{7})[A-Z]$")


class CertificateInvalid(Exception):
    """The .p12 cannot be used to present to the AEAT. ``code`` says why (``unopenable``, ``incomplete``,
    ``no_client_auth``); the message names the reason only."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class StorageUnavailable(Exception):
    """This server has no usable ``FISCAL_CERTIFICATE_KEY``: no certificate can be kept."""


class CertificateUnreadable(Exception):
    """A kept certificate cannot be opened: the key is missing or is not the one that sealed it."""


@dataclass(frozen=True)
class CertificateFacts:
    holder: str
    holder_tax_id: str
    kind: Kind
    expires_at: dt.datetime


def inspect(p12: bytes, password: str) -> CertificateFacts:
    """What the .p12 says; ``CertificateInvalid`` if its password does not open it or it cannot present."""
    try:
        key, certificate, _chain = pkcs12.load_key_and_certificates(
            p12, password.encode() or None
        )
    except ValueError, TypeError, UnsupportedAlgorithm:
        raise CertificateInvalid(
            "unopenable",
            "The file is not a .p12/.pfx certificate that this password opens.",
        ) from None
    has_key = key is not None
    del key
    if certificate is None or not has_key:
        raise CertificateInvalid(
            "incomplete", "The file does not hold a certificate and its private key."
        )
    if _declares_eku_without_client_auth(certificate):
        raise CertificateInvalid(
            "no_client_auth",
            "The certificate does not allow client authentication, so it cannot connect to the AEAT.",
        )
    organization_id = _attribute(certificate, NameOID.ORGANIZATION_IDENTIFIER)
    serial = _attribute(certificate, NameOID.SERIAL_NUMBER)
    common_name = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return CertificateFacts(
        holder=str(common_name[0].value).strip() if common_name else "",
        holder_tax_id=organization_id or serial,
        kind=_kind(certificate, organization_id, serial),
        expires_at=certificate.not_valid_after_utc,
    )


def generate_key() -> str:
    """A new ``FISCAL_CERTIFICATE_KEY`` (32 random bytes, URL-safe base64)."""
    return Fernet.generate_key().decode()


def storage_available() -> bool:
    """Whether this server can keep a certificate (it has a valid ``FISCAL_CERTIFICATE_KEY``)."""
    return _fernet() is not None


def seal(p12: bytes, password: str) -> bytes:
    """The .p12 and its password, encrypted together; ``StorageUnavailable`` without a usable key."""
    fernet = _fernet()
    if fernet is None:
        raise StorageUnavailable(
            "FISCAL_CERTIFICATE_KEY is not set or is not a Fernet key."
        )
    clear = json.dumps(
        {"p12": base64.b64encode(p12).decode(), "password": password}
    ).encode()
    return fernet.encrypt(clear)


def open(blob: bytes) -> tuple[bytes, str]:
    """The .p12 and its password ``seal`` kept; ``CertificateUnreadable`` if this key cannot open them."""
    fernet = _fernet()
    if fernet is None:
        raise CertificateUnreadable(
            "FISCAL_CERTIFICATE_KEY is not set or is not a Fernet key."
        )
    try:
        kept = json.loads(fernet.decrypt(bytes(blob)))
        return base64.b64decode(kept["p12"], validate=True), str(kept["password"])
    except InvalidToken, ValueError, KeyError, TypeError, binascii.Error:
        raise CertificateUnreadable(
            "The kept certificate cannot be opened with this server's key."
        ) from None


def material(blob: bytes) -> gateway.Certificate:
    """What the gateway takes to present with the kept certificate; ``CertificateUnreadable`` as ``open``."""
    p12, password = open(blob)
    return gateway.Certificate(
        p12_base64=base64.b64encode(p12).decode(), password=password
    )


def _fernet() -> Fernet | None:
    key = str(getattr(settings, "FISCAL_CERTIFICATE_KEY", "") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key)
    except ValueError, TypeError, binascii.Error:
        return None


def _attribute(certificate: x509.Certificate, oid: x509.ObjectIdentifier) -> str:
    """The subject's first ``oid`` without its ETSI prefix, upper case; empty if it has none."""
    values = certificate.subject.get_attributes_for_oid(oid)
    if not values:
        return ""
    return _ETSI_PREFIX.sub("", str(values[0].value).strip().upper())


def _declares_eku_without_client_auth(certificate: x509.Certificate) -> bool:
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
    except x509.ExtensionNotFound:
        return False
    return not (
        ExtendedKeyUsageOID.CLIENT_AUTH in usages
        or ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE in usages
    )


def _kind(certificate: x509.Certificate, organization_id: str, serial: str) -> Kind:
    der = certificate.public_bytes(serialization.Encoding.DER)
    if _QC_TYPE_ESEAL in der and _QC_TYPE_ESIGN not in der:
        return "seal"
    person = bool(_PERSON_ID.match(serial))
    if organization_id and person:
        return "representative"
    if not organization_id and person:
        return "personal"
    return "unknown"
