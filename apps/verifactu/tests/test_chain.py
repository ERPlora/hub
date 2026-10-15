"""The chain's bricks (VERIFACTU-F13, F18, F26): the AEAT formats, the SHA-256 fingerprint and the QR link.

The official vectors are the three cases of «Detalle de las especificaciones técnicas para generación de la
huella o hash de los registros de facturación» v0.1.2 (27/08/2024, §6): an alta, the next one chained to it
and an anulación chained to the second, published input → published hash. The derived anchors and the QR
cases are the current engine's (hub ``crates/plugins/verifactu/tests/aeat_compliance.rs``), recomputed here
with an independent oracle. The 19 real submissions the AEAT's preproduction accepted are checked in
``test_envelope.py``.
"""

import datetime as dt
import hashlib
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.verifactu import chain

NIF = "B12345678"
NUM1 = "FA2026/001"
NUM2 = "FA2026/002"
DATE = dt.date(2026, 6, 10)
TS1 = "2026-06-10T12:34:56+00:00"
TS2 = "2026-06-10T13:00:00+00:00"

CASE_1 = "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"
CASE_2 = "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"
CASE_3 = "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


def oracle(text: str) -> str:
    """An independent SHA-256 upper-hex: never the module's own function."""
    return hashlib.sha256(text.encode()).hexdigest().upper()


# Formats


def test_a_date_goes_day_month_year():
    assert chain.format_date(dt.date(2026, 6, 10)) == "10-06-2026"
    assert chain.format_date(dt.date(2026, 1, 1)) == "01-01-2026"


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (23100, "231.00"),
        (0, "0.00"),
        (133100, "1331.00"),
        (1, "0.01"),
        (4205, "42.05"),
        (-1210, "-12.10"),
    ],
)
def test_an_amount_is_euros_with_two_decimals_and_a_point(cents, text):
    assert chain.format_amount(cents) == text


def test_a_rate_keeps_its_two_decimals():
    assert chain.format_rate(Decimal("21")) == "21.00"
    assert chain.format_rate("5.2") == "5.20"
    assert chain.format_rate(Decimal("7.5")) == "7.50"


def test_the_generation_time_has_whole_seconds_and_its_offset():
    madrid = ZoneInfo("Europe/Madrid")
    moment = dt.datetime(2026, 9, 22, 19, 58, 55, 789000, tzinfo=madrid)
    assert chain.format_timestamp(moment) == "2026-09-22T19:58:55+02:00"
    winter = dt.datetime(2026, 1, 5, 9, 0, 0, tzinfo=madrid)
    assert chain.format_timestamp(winter) == "2026-01-05T09:00:00+01:00"


def test_a_naive_time_is_refused():
    with pytest.raises(ValueError):
        chain.format_timestamp(dt.datetime(2026, 1, 5, 9, 0, 0))


def test_parse_date_reads_the_aeat_and_the_iso_forms():
    assert chain.parse_date("01-08-2026") == dt.date(2026, 8, 1)
    assert chain.parse_date("2026-08-01") == dt.date(2026, 8, 1)


# The official AEAT vectors (§6, cases 1–3: one chain)


def test_the_official_case_1_and_case_2_altas():
    case_1 = chain.alta_hash(
        issuer_nif="89890001K",
        number="12345678/G33",
        issue_date=dt.date(2024, 1, 1),
        invoice_type="F1",
        tax_amount=1235,
        total_amount=12345,
        previous_hash="",
        generated_at="2024-01-01T19:20:30+01:00",
    )
    assert case_1 == CASE_1
    assert (
        oracle(
            "IDEmisorFactura=89890001K&NumSerieFactura=12345678/G33&FechaExpedicionFactura=01-01-2024"
            "&TipoFactura=F1&CuotaTotal=12.35&ImporteTotal=123.45&Huella="
            "&FechaHoraHusoGenRegistro=2024-01-01T19:20:30+01:00"
        )
        == CASE_1
    )
    case_2 = chain.alta_hash(
        issuer_nif="89890001K",
        number="12345679/G34",
        issue_date=dt.date(2024, 1, 1),
        invoice_type="F1",
        tax_amount=1235,
        total_amount=12345,
        previous_hash=case_1,
        generated_at="2024-01-01T19:20:35+01:00",
    )
    assert case_2 == CASE_2


def test_the_official_case_3_anulacion_chains_to_case_2():
    case_3 = chain.anulacion_hash(
        issuer_nif="89890001K",
        number="12345679/G34",
        issue_date=dt.date(2024, 1, 1),
        previous_hash=CASE_2,
        generated_at="2024-01-01T19:20:40+01:00",
    )
    assert case_3 == CASE_3
    assert (
        oracle(
            "IDEmisorFacturaAnulada=89890001K&NumSerieFacturaAnulada=12345679/G34"
            "&FechaExpedicionFacturaAnulada=01-01-2024&Huella="
            + CASE_2
            + "&FechaHoraHusoGenRegistro=2024-01-01T19:20:40+01:00"
        )
        == CASE_3
    )


# Derived anchors (the current engine's, recomputed with the oracle)


def alta(number=NUM1, tax=23100, total=133100, previous="", ts=TS1):
    return chain.alta_hash(
        issuer_nif=NIF,
        number=number,
        issue_date=DATE,
        invoice_type="F1",
        tax_amount=tax,
        total_amount=total,
        previous_hash=previous,
        generated_at=ts,
    )


def test_the_alta_follows_the_aeat_field_order():
    expected = oracle(
        f"IDEmisorFactura={NIF}&NumSerieFactura={NUM1}&FechaExpedicionFactura=10-06-2026&TipoFactura=F1"
        f"&CuotaTotal=231.00&ImporteTotal=1331.00&Huella=&FechaHoraHusoGenRegistro={TS1}"
    )
    assert (
        expected == "A84E25C35B6BA9FDABE7CF8DD744AA23A4BA8E3E2FE6535C71A9572B418D9122"
    )
    assert alta() == expected


def test_the_fingerprint_is_64_upper_hex():
    value = alta()
    assert len(value) == 64
    assert value == value.upper()
    assert chain.is_valid_hash(value)


def test_the_fingerprint_is_computed_in_euros_not_cents():
    # 23100 cents are 231.00 €: declaring 23100.00 would be another fingerprint (a regression of the
    # conversion would change every hash of the chain).
    wrong = oracle(
        f"IDEmisorFactura={NIF}&NumSerieFactura={NUM1}&FechaExpedicionFactura=10-06-2026&TipoFactura=F1"
        f"&CuotaTotal=23100.00&ImporteTotal=133100.00&Huella=&FechaHoraHusoGenRegistro={TS1}"
    )
    assert alta() != wrong


def test_record_n_carries_the_fingerprint_of_record_n_minus_1():
    first = alta()
    second = alta(number=NUM2, tax=4200, total=24200, previous=first, ts=TS2)
    assert second == oracle(
        f"IDEmisorFactura={NIF}&NumSerieFactura={NUM2}&FechaExpedicionFactura=10-06-2026&TipoFactura=F1"
        f"&CuotaTotal=42.00&ImporteTotal=242.00&Huella={first}&FechaHoraHusoGenRegistro={TS2}"
    )
    assert second == "718F7F017C633C8471F8DB1B4413EF8B1A3B38231E97320AEFC9B9E26CE13033"
    assert alta(number=NUM2, tax=4200, total=24200, previous="OTHER", ts=TS2) != second


def test_the_anulacion_omits_type_and_amounts_and_names_its_fields_anulada():
    value = chain.anulacion_hash(
        issuer_nif=NIF, number=NUM1, issue_date=DATE, previous_hash="", generated_at=TS1
    )
    assert value == oracle(
        f"IDEmisorFacturaAnulada={NIF}&NumSerieFacturaAnulada={NUM1}"
        f"&FechaExpedicionFacturaAnulada=10-06-2026&Huella=&FechaHoraHusoGenRegistro={TS1}"
    )
    assert value == "BF697C1BE3F2A38B8A008037F9B745B40BC852D0579F6D932AB83AD0E29E1B3B"
    assert value != alta()


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        ("A" * 64, True),
        ("a1" * 32, True),
        ("A" * 63, False),
        ("G" * 64, False),
        ("", False),
        (" " + "A" * 63, False),
    ],
)
def test_a_valid_fingerprint_is_64_hexadecimal_characters(text, valid):
    assert chain.is_valid_hash(text) is valid


def test_an_imported_fingerprint_is_normalised_to_upper_case():
    assert chain.normalize_hash(" " + "ab" * 32 + "\n") == "AB" * 32


# The QR (VERIFACTU-F18)


def test_the_production_qr_goes_to_the_real_site_with_its_four_parameters():
    url = chain.qr_url(
        issuer_nif=NIF,
        number=NUM1,
        issue_date=DATE,
        total_amount=133100,
        environment="production",
    )
    assert url == (
        "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR"
        "?nif=B12345678&numserie=FA2026%2F001&fecha=10-06-2026&importe=1331.00"
    )


def test_the_testing_qr_goes_to_the_test_site():
    url = chain.qr_url(
        issuer_nif=NIF,
        number=NUM1,
        issue_date=DATE,
        total_amount=23100,
        environment="testing",
    )
    assert url.startswith("https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?")
    assert "importe=231.00" in url


def test_anything_but_production_is_the_test_site():
    url = chain.qr_url(
        issuer_nif=NIF, number=NUM1, issue_date=DATE, total_amount=100, environment=""
    )
    assert url.startswith("https://prewww2.aeat.es/")


def test_the_qr_encodes_every_reserved_character():
    url = chain.qr_url(
        issuer_nif=NIF,
        number="T 1&2+ñ",
        issue_date=DATE,
        total_amount=-1210,
        environment="testing",
    )
    assert "numserie=T%201%262%2B%C3%B1" in url
    assert "importe=-12.10" in url


def test_the_qr_image_is_an_svg_data_uri_of_the_link():
    image = chain.qr_svg_data_uri(
        "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345678"
    )
    assert image.startswith("data:image/svg+xml;base64,")
    import base64

    svg = base64.b64decode(image.split(",", 1)[1]).decode()
    assert "<svg" in svg and "</svg>" in svg
