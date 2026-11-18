"""The certification authorities the AEAT recognises: the issuing CAs of qualified certificates for electronic
signatures and seals in Spain's trusted list (the Ministry's TSL, under eIDAS), kept in ``trusted_authorities.json``
and renewed with ``manage.py verifactu_trusted_list``. Nothing here reaches the network.

A certificate is recognised when one of them signed it while that authority was qualified: one withdrawn later still
vouches for what it issued before. Spain's list names each issuing CA itself, so the certificate's own issuer has to
be on it; a matching name with another key is not.
"""

import base64
import datetime as dt
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature

LIST_FILE = Path(__file__).with_name("trusted_authorities.json")


@dataclass(frozen=True)
class Authority:
    certificate: x509.Certificate
    withdrawn_at: dt.datetime | None = None


@dataclass(frozen=True)
class TrustedList:
    sequence: int
    authorities: tuple[Authority, ...]


@cache
def kept() -> TrustedList:
    """The list kept in the app, read once per process."""
    data = json.loads(LIST_FILE.read_text())
    return TrustedList(
        sequence=int(data["sequence"]),
        authorities=tuple(
            Authority(
                certificate=x509.load_der_x509_certificate(base64.b64decode(entry["certificate"])),
                withdrawn_at=dt.datetime.fromisoformat(entry["withdrawn_at"]) if entry["withdrawn_at"] else None,
            )
            for entry in data["authorities"]
        ),
    )


def authorities() -> tuple[Authority, ...]:
    return kept().authorities


def sequence() -> int:
    """The number of the trusted list the kept one was read from: a certificate checked against another is checked
    again."""
    return kept().sequence


def recognised(certificate: x509.Certificate) -> bool:
    return any(_vouches(authority, certificate) for authority in authorities())


def _vouches(authority: Authority, certificate: x509.Certificate) -> bool:
    try:
        certificate.verify_directly_issued_by(authority.certificate)
    except ValueError, TypeError, InvalidSignature:
        return False
    return authority.withdrawn_at is None or certificate.not_valid_before_utc < authority.withdrawn_at
