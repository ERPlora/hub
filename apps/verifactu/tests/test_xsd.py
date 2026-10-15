"""The real AEAT schemas (VERIFACTU-F13, F15): every record is checked against ``SuministroLR.xsd`` (which
imports ``SuministroInformacion.xsd`` and the XML signature schema) before it is sealed and before it is sent.

The schemas are the AEAT's, kept in ``apps/verifactu/xsd`` (pinned by their SHA-256 below) and read locally in
``sandbox`` mode: validating never reaches the network. The 19 submissions the AEAT's preproduction accepted
validate; what the AEAT would refuse with a 4102 does not.
"""

import datetime as dt
import hashlib
from pathlib import Path

import pytest

from apps.verifactu import envelope, xsd
from apps.verifactu.envelope import (
    AltaData,
    AnulacionData,
    ChainLink,
    InvoiceRef,
    SystemInfo,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMAS = Path(xsd.__file__).parent / "xsd"
SYSTEM = SystemInfo(
    name="ERPLORA CLOUD SL",
    nif="B27593136",
    system_name="ERPlora Hub",
    system_id="EC",
    version="dev",
    installation="a",
    only_verifactu="S",
    multi_ot="S",
    multiple_ot="N",
)
DAY = dt.date(2026, 10, 14)
TS = "2026-10-14T10:00:00+02:00"
VAT21 = {
    "tax": "vat",
    "regime": "01",
    "qualification": "subject",
    "exempt_reason": "",
    "rate": "21.00",
    "surcharge_rate": "0.00",
    "base": 1000,
    "quota": 210,
    "surcharge_quota": 0,
}


def test_the_schemas_are_the_ones_pinned():
    digests = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(SCHEMAS.glob("*.xsd"))
    }
    assert digests == {
        # The AEAT's query schema (ConsultaLR.xsd, downloaded from its site on 2026-10-15).
        "ConsultaLR.xsd": "bf2cdb8fc4b95b291757a72b76d8fffca06a6d30d9329122ca2fd6b2d5f8f1b1",
        "SuministroInformacion.xsd": "ee4c1655175644de44c4c25055ffeb8e5f4bb4bc3834ce8254d4222ef18c8aa1",
        "SuministroLR.xsd": "cbdac8d427cc5ab5d77ca48974cab0f35d6bb819c4c66db361681e3710aeba36",
        "xmldsig-core-schema.xsd": "d102ad3df7664c307e0c2c776ba4a90513b1969974d8a940bae1a77f9f21e15d",
    }


def test_the_signature_schema_is_read_from_disk_never_from_the_network():
    namespaces = xsd.schema().maps.namespaces
    assert "http://www.w3.org/2000/09/xmldsig#" in namespaces
    locations = [
        component.url for component in namespaces["http://www.w3.org/2000/09/xmldsig#"]
    ]
    assert locations and all(
        url.startswith("file://") and url.endswith("/xsd/xmldsig-core-schema.xsd")
        for url in locations
    )


@pytest.mark.parametrize(
    "path", sorted(FIXTURES.glob("*_sent_*.xml")), ids=lambda path: path.stem
)
def test_every_submission_the_aeat_accepted_validates(path):
    xsd.validate(path.read_text(encoding="utf-8"))


def whole(*registros, **header) -> str:
    return envelope.submission(
        obligado_name="Peluquería Ana SL",
        obligado_nif="B12345674",
        registros=list(registros),
        **header,
    )


def alta(**more) -> str:
    fields = {
        "issuer_nif": "B12345674",
        "issuer_name": "Peluquería Ana SL",
        "number": "TICKET-2026-000001",
        "issue_date": DAY,
        "invoice_type": "F2",
        "description": "Venta 20261014-0001",
        "tax_breakdown": [VAT21],
        "tax_amount": 210,
        "total_amount": 1210,
    }
    fields.update(more)
    previous = ChainLink(
        "B12345674", "TICKET-2026-000000", dt.date(2026, 10, 13), "B" * 64
    )
    return envelope.registro_alta(
        AltaData(**fields),
        previous=previous,
        system=SYSTEM,
        generated_at=TS,
        fingerprint="A" * 64,
    )


def test_every_kind_of_record_this_app_builds_validates():
    records = [
        alta(),
        alta(
            invoice_type="F1",
            number="FACT-2026-000001",
            recipient_name="Talleres SL",
            recipient_tax_id="B12345674",
            operation_date=dt.date(2026, 10, 13),
        ),
        alta(
            invoice_type="F3",
            number="FACT-2026-000002",
            substituted=(InvoiceRef("B12345674", "TICKET-2026-000001", DAY),),
            recipient_name="GmbH",
            recipient_tax_id="123456789",
            recipient_country="DE",
        ),
        alta(
            invoice_type="R5",
            number="RECT-2026-000001",
            rectification_kind="I",
            rectified=(InvoiceRef("B12345674", "TICKET-2026-000001", DAY),),
            tax_breakdown=[{**VAT21, "base": -1000, "quota": -210}],
            tax_amount=-210,
            total_amount=-1210,
        ),
        alta(number="TICKET-2026-000003", correction=True, previous_rejection="S"),
        alta(number="TICKET-2026-000005", correction=True, previous_rejection="X"),
        alta(
            number="TICKET-2026-000004",
            tax_breakdown=[
                {**VAT21, "surcharge_rate": "5.20", "surcharge_quota": 52},
                {
                    **VAT21,
                    "qualification": "exempt",
                    "exempt_reason": "E1",
                    "rate": "0.00",
                    "quota": 0,
                },
                {
                    **VAT21,
                    "qualification": "subject_reverse",
                    "rate": "0.00",
                    "quota": 0,
                },
                {
                    **VAT21,
                    "qualification": "not_subject_location",
                    "rate": "0.00",
                    "quota": 0,
                },
            ],
            tax_amount=262,
            total_amount=4262,
        ),
        envelope.registro_anulacion(
            AnulacionData("B12345674", "TICKET-2026-000001", DAY),
            previous=None,
            system=SYSTEM,
            generated_at=TS,
            fingerprint="C" * 64,
        ),
    ]
    xsd.validate(
        whole(*records, representative=("ERPLORA CLOUD SL", "B27593136"), incident=True)
    )


@pytest.mark.parametrize(
    ("change", "element"),
    [
        (
            (
                "<sum1:TipoFactura>F2</sum1:TipoFactura>",
                "<sum1:TipoFactura>F9</sum1:TipoFactura>",
            ),
            "TipoFactura",
        ),
        (("Venta 20261014-0001", "x" * 501), "DescripcionOperacion"),
        (
            (
                "<sum1:TipoHuella>01</sum1:TipoHuella>",
                "<sum1:TipoHuella>02</sum1:TipoHuella>",
            ),
            "TipoHuella",
        ),
        (
            (
                "<sum1:ImporteTotal>12.10</sum1:ImporteTotal>",
                "<sum1:ImporteTotal>12.105</sum1:ImporteTotal>",
            ),
            "ImporteTotal",
        ),
        (("<sum1:IDVersion>1.0</sum1:IDVersion>", ""), "IDVersion"),
    ],
)
def test_what_the_aeat_would_refuse_with_a_4102_is_refused_here(change, element):
    xml = whole(alta()).replace(*change, 1)
    with pytest.raises(xsd.SchemaError) as refused:
        xsd.validate(xml)
    assert element in str(refused.value)


def test_a_document_that_is_no_submission_is_refused():
    with pytest.raises(xsd.SchemaError):
        xsd.validate(
            "<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/'/>"
        )
    with pytest.raises(xsd.SchemaError):
        xsd.validate("not xml at all")


def test_a_single_record_is_validated_inside_its_own_envelope():
    xsd.validate_record(
        alta(), obligado_name="Peluquería Ana SL", obligado_nif="B12345674"
    )
    with pytest.raises(xsd.SchemaError):
        xsd.validate_record(
            alta().replace(">F2<", ">F9<"),
            obligado_name="Peluquería Ana SL",
            obligado_nif="B12345674",
        )


# The query (VERIFACTU-F27, F28)


def test_a_query_and_its_next_page_pass_the_aeats_query_schema():
    first = envelope.query(obligado_nif="B12345674", obligado_name="Ana", year=2026, month=8)
    xsd.validate_query(first)
    after = envelope.InvoiceRef("B12345674", "TICKET-2026-009999", DAY)
    xsd.validate_query(
        envelope.query(
            obligado_nif="B12345674", obligado_name="Ana", year=2026, month=8, represented=True, after=after
        )
    )


def test_a_query_out_of_the_schema_does_not_pass():
    with pytest.raises(xsd.SchemaError, match="Periodo"):
        xsd.validate_query(
            envelope.query(obligado_nif="B12345674", obligado_name="Ana", year=2026, month=13)
        )
