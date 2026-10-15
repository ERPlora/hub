"""The VeriFactu chain's bricks (RD 1007/2023, Orden HAC/1177/2024): the AEAT formats, the SHA-256
fingerprint of an alta and of an anulación, and the QR link.

Pure functions, no ORM. Ported from the current engine (hub ``crates/plugins/verifactu/src/chain.rs``), which
reproduces the three official vectors of «Detalle de las especificaciones técnicas para generación de la huella
o hash de los registros de facturación» v0.1.2 and was accepted by the AEAT's preproduction.

- Amounts travel in whole cents (with their sign) and become euros with two decimals and a point only here,
  at the fiscal boundary.
- The fingerprint is the upper-case hex SHA-256 of ``field=value`` pairs joined by ``&``, in the exact order
  of the specification; an anulación names its identification fields ``…Anulada`` and carries no type nor
  amounts.
- The QR goes to the AEAT's site of the record's environment: ``production`` → the real site; anything else
  → the test site (a QR of the test environment with the real host would never validate, and a record never
  goes to production by mistake).
"""

import base64
import datetime as dt
import hashlib
from decimal import Decimal
from urllib.parse import quote

import qrcode
import qrcode.constants
import qrcode.image.svg

PRODUCTION = "production"
TESTING = "testing"
QR_HOSTS = {
    PRODUCTION: "https://www2.agenciatributaria.gob.es",
    TESTING: "https://prewww2.aeat.es",
}
QR_PATH = "/wlpl/TIKE-CONT/ValidarQR"
HASH_LENGTH = 64
_HEX = frozenset("0123456789abcdefABCDEF")
_CENT = Decimal("0.01")


def format_date(date: dt.date) -> str:
    """``FechaExpedicionFactura``: ``DD-MM-YYYY``."""
    return date.strftime("%d-%m-%Y")


def parse_date(text: str) -> dt.date:
    """A date the AEAT writes (``DD-MM-YYYY``) or an ISO one (``YYYY-MM-DD``)."""
    text = text.strip()
    if len(text) == 10 and text[2] == "-" and text[5] == "-":
        return dt.datetime.strptime(text, "%d-%m-%Y").date()
    return dt.date.fromisoformat(text)


def format_amount(cents: int) -> str:
    """An amount in cents as the AEAT wants it: euros, two decimals and a point (``-12.10``)."""
    return str((Decimal(int(cents)) / 100).quantize(_CENT))


def format_rate(rate: Decimal | str | int | float) -> str:
    """A percentage (``TipoImpositivo``, ``TipoRecargoEquivalencia``) with two decimals: ``21.00``."""
    return str(Decimal(str(rate)).quantize(_CENT))


def format_timestamp(moment: dt.datetime) -> str:
    """``FechaHoraHusoGenRegistro``: ISO 8601 with whole seconds and its offset (``2026-09-22T19:58:55+02:00``)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("The generation time of a record needs its time zone.")
    return moment.replace(microsecond=0).isoformat(timespec="seconds")


def _sha256_upper(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def alta_hash(
    *,
    issuer_nif: str,
    number: str,
    issue_date: dt.date,
    invoice_type: str,
    tax_amount: int,
    total_amount: int,
    previous_hash: str,
    generated_at: str,
) -> str:
    """The fingerprint of an alta record (amounts in cents)."""
    return _sha256_upper(
        f"IDEmisorFactura={issuer_nif}"
        f"&NumSerieFactura={number}"
        f"&FechaExpedicionFactura={format_date(issue_date)}"
        f"&TipoFactura={invoice_type}"
        f"&CuotaTotal={format_amount(tax_amount)}"
        f"&ImporteTotal={format_amount(total_amount)}"
        f"&Huella={previous_hash}"
        f"&FechaHoraHusoGenRegistro={generated_at}"
    )


def anulacion_hash(
    *,
    issuer_nif: str,
    number: str,
    issue_date: dt.date,
    previous_hash: str,
    generated_at: str,
) -> str:
    """The fingerprint of an anulación record: the ``…Anulada`` field names, no type and no amounts."""
    return _sha256_upper(
        f"IDEmisorFacturaAnulada={issuer_nif}"
        f"&NumSerieFacturaAnulada={number}"
        f"&FechaExpedicionFacturaAnulada={format_date(issue_date)}"
        f"&Huella={previous_hash}"
        f"&FechaHoraHusoGenRegistro={generated_at}"
    )


def is_valid_hash(text: str) -> bool:
    """A VeriFactu fingerprint: exactly 64 hexadecimal characters."""
    return len(text) == HASH_LENGTH and all(char in _HEX for char in text)


def normalize_hash(text: str) -> str:
    """An imported fingerprint in the chain's canonical form (trimmed, upper case)."""
    return text.strip().upper()


def qr_url(
    *,
    issuer_nif: str,
    number: str,
    issue_date: dt.date,
    total_amount: int,
    environment: str,
) -> str:
    """The AEAT's verification link of a record (its QR), on the site of the record's environment."""
    host = QR_HOSTS[PRODUCTION] if environment == PRODUCTION else QR_HOSTS[TESTING]
    query = "&".join(
        f"{name}={quote(value, safe='')}"
        for name, value in (
            ("nif", issuer_nif),
            ("numserie", number),
            ("fecha", format_date(issue_date)),
            ("importe", format_amount(total_amount)),
        )
    )
    return f"{host}{QR_PATH}?{query}"


def qr_svg_data_uri(url: str) -> str:
    """The QR of ``url`` (ISO/IEC 18004, error correction M, as the AEAT asks) as an SVG ``data:`` URI."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    code.add_data(url)
    code.make(fit=True)
    svg = code.make_image(image_factory=qrcode.image.svg.SvgPathImage).to_string()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
