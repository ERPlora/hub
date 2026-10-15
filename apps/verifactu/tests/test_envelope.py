"""The XML of a record and of a submission (VERIFACTU-F13–F15, F24, F27, F30).

**Golden**: the 19 envelopes the current engine sent to the AEAT's preproduction and the AEAT accepted
(``fixtures/*_sent_*.xml``, hub ``crates/plugins/verifactu/tests/fixtures``) are rebuilt from their own data and
must come out identical, byte for byte, and their fingerprints must be the ones this chain computes. The rest
pins what the engine did not emit (FechaOperacion, Subsanacion, RechazoPrevio, a batch, the incidence and the
representative) and the rules of the breakdown, the recipient and the rectification blocks.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from apps.verifactu import chain, envelope
from apps.verifactu.envelope import (
    AltaData,
    AnulacionData,
    ChainLink,
    InvoiceRef,
    SystemInfo,
)

FIXTURES = Path(__file__).parent / "fixtures"
SENT = sorted(FIXTURES.glob("*_sent_*.xml"))
NS = {
    "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
    "sum": envelope.SUM,
    "sum1": envelope.SUM1,
}
TAXES = {"01": "vat", "02": "ipsi", "03": "igic", "05": "other"}
QUALIFICATIONS = {
    "S1": "subject",
    "S2": "subject_reverse",
    "N1": "not_subject",
    "N2": "not_subject_location",
}


def cents(text: str) -> int:
    return int((Decimal(text) * 100).to_integral_value())


def text(node, path: str, default: str = "") -> str:
    found = node.find(path, NS)
    return found.text if found is not None and found.text is not None else default


def breakdown_of(alta) -> list[dict]:
    """The XML's DetalleDesglose back to Invoicing's breakdown entries (WORKBOOK «Contrato con Facturación»)."""
    entries = []
    for detail in alta.findall("sum1:Desglose/sum1:DetalleDesglose", NS):
        exempt = text(detail, "sum1:OperacionExenta")
        entries.append(
            {
                "tax": TAXES[text(detail, "sum1:Impuesto")],
                "regime": text(detail, "sum1:ClaveRegimen"),
                "qualification": "exempt"
                if exempt
                else QUALIFICATIONS[text(detail, "sum1:CalificacionOperacion")],
                "exempt_reason": exempt,
                "rate": text(detail, "sum1:TipoImpositivo", "0.00"),
                "surcharge_rate": text(detail, "sum1:TipoRecargoEquivalencia", "0.00"),
                "base": cents(text(detail, "sum1:BaseImponibleOimporteNoSujeto")),
                "quota": cents(text(detail, "sum1:CuotaRepercutida", "0")),
                "surcharge_quota": cents(
                    text(detail, "sum1:CuotaRecargoEquivalencia", "0")
                ),
            }
        )
    return entries


def recipient_of(alta) -> dict:
    who = alta.find("sum1:Destinatarios/sum1:IDDestinatario", NS)
    if who is None:
        return {}
    other = who.find("sum1:IDOtro", NS)
    if other is None:
        return {
            "recipient_name": text(who, "sum1:NombreRazon"),
            "recipient_tax_id": text(who, "sum1:NIF"),
        }
    return {
        "recipient_name": text(who, "sum1:NombreRazon"),
        "recipient_tax_id": text(other, "sum1:ID"),
        "recipient_country": text(other, "sum1:CodigoPais"),
        "recipient_id_type": text(other, "sum1:IDType"),
    }


def rebuilt(path: Path) -> tuple[str, str, str]:
    """(the sent bytes, the envelope rebuilt from their data, the fingerprint this chain computes)."""
    sent = path.read_text(encoding="utf-8").rstrip("\n")
    root = ET.fromstring(sent)
    header = root.find(".//sum:Cabecera/sum1:ObligadoEmision", NS)
    alta = root.find(".//sum1:RegistroAlta", NS)
    data = AltaData(
        issuer_nif=text(alta, "sum1:IDFactura/sum1:IDEmisorFactura"),
        issuer_name=text(alta, "sum1:NombreRazonEmisor"),
        number=text(alta, "sum1:IDFactura/sum1:NumSerieFactura"),
        issue_date=chain.parse_date(
            text(alta, "sum1:IDFactura/sum1:FechaExpedicionFactura")
        ),
        invoice_type=text(alta, "sum1:TipoFactura"),
        description=text(alta, "sum1:DescripcionOperacion"),
        tax_breakdown=breakdown_of(alta),
        tax_amount=cents(text(alta, "sum1:CuotaTotal")),
        total_amount=cents(text(alta, "sum1:ImporteTotal")),
        **recipient_of(alta),
    )
    anterior = alta.find("sum1:Encadenamiento/sum1:RegistroAnterior", NS)
    previous = (
        None
        if anterior is None
        else ChainLink(
            issuer_nif=text(anterior, "sum1:IDEmisorFactura"),
            number=text(anterior, "sum1:NumSerieFactura"),
            issue_date=chain.parse_date(text(anterior, "sum1:FechaExpedicionFactura")),
            fingerprint=text(anterior, "sum1:Huella"),
        )
    )
    info = alta.find("sum1:SistemaInformatico", NS)
    system = SystemInfo(
        name=text(info, "sum1:NombreRazon"),
        nif=text(info, "sum1:NIF"),
        system_name=text(info, "sum1:NombreSistemaInformatico"),
        system_id=text(info, "sum1:IdSistemaInformatico"),
        version=text(info, "sum1:Version"),
        installation=text(info, "sum1:NumeroInstalacion"),
        only_verifactu=text(info, "sum1:TipoUsoPosibleSoloVerifactu"),
        multi_ot=text(info, "sum1:TipoUsoPosibleMultiOT"),
        multiple_ot=text(info, "sum1:IndicadorMultiplesOT"),
    )
    generated_at = text(alta, "sum1:FechaHoraHusoGenRegistro")
    fingerprint = chain.alta_hash(
        issuer_nif=data.issuer_nif,
        number=data.number,
        issue_date=data.issue_date,
        invoice_type=data.invoice_type,
        tax_amount=data.tax_amount,
        total_amount=data.total_amount,
        previous_hash=previous.fingerprint if previous else "",
        generated_at=generated_at,
    )
    registro = envelope.registro_alta(
        data,
        previous=previous,
        system=system,
        generated_at=generated_at,
        fingerprint=fingerprint,
    )
    whole = envelope.submission(
        obligado_name=text(header, "sum1:NombreRazon"),
        obligado_nif=text(header, "sum1:NIF"),
        registros=[registro],
    )
    return sent, whole, fingerprint


def test_there_are_nineteen_golden_submissions():
    assert len(SENT) == 19


@pytest.mark.parametrize("path", SENT, ids=lambda path: path.stem)
def test_an_accepted_submission_is_rebuilt_byte_for_byte(path):
    sent, whole, _ = rebuilt(path)
    assert whole == sent


@pytest.mark.parametrize("path", SENT, ids=lambda path: path.stem)
def test_the_fingerprint_the_aeat_accepted_is_the_one_this_chain_computes(path):
    sent, _, fingerprint = rebuilt(path)
    alta = ET.fromstring(sent).find(".//sum1:RegistroAlta", NS)
    assert text(alta, "sum1:Huella") == fingerprint


# What the engine did not emit, and the rules


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
    "regime": "",
    "qualification": "subject",
    "exempt_reason": "",
    "rate": "21.00",
    "surcharge_rate": "0.00",
    "base": 1000,
    "quota": 210,
    "surcharge_quota": 0,
}


def ticket(**more) -> AltaData:
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
    return AltaData(**fields)


def alta_xml(data: AltaData, previous: ChainLink | None = None) -> str:
    return envelope.registro_alta(
        data, previous=previous, system=SYSTEM, generated_at=TS, fingerprint="A" * 64
    )


def test_an_empty_regime_is_the_general_one_and_the_rate_has_two_decimals():
    xml = alta_xml(ticket())
    assert (
        "<sum1:DetalleDesglose><sum1:Impuesto>01</sum1:Impuesto><sum1:ClaveRegimen>01</sum1:ClaveRegimen>"
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion><sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>"
        "<sum1:BaseImponibleOimporteNoSujeto>10.00</sum1:BaseImponibleOimporteNoSujeto>"
        "<sum1:CuotaRepercutida>2.10</sum1:CuotaRepercutida></sum1:DetalleDesglose>"
    ) in xml


def test_a_zero_surcharge_is_no_surcharge():
    assert "RecargoEquivalencia" not in alta_xml(ticket())


def test_a_surcharge_travels_inside_its_vat_line():
    line = {**VAT21, "surcharge_rate": "5.20", "surcharge_quota": 52}
    xml = alta_xml(ticket(tax_breakdown=[line], tax_amount=262, total_amount=1262))
    assert (
        "<sum1:CuotaRepercutida>2.10</sum1:CuotaRepercutida>"
        "<sum1:TipoRecargoEquivalencia>5.20</sum1:TipoRecargoEquivalencia>"
        "<sum1:CuotaRecargoEquivalencia>0.52</sum1:CuotaRecargoEquivalencia>"
    ) in xml
    assert "<sum1:TipoImpositivo>5.20</sum1:TipoImpositivo>" not in xml


def test_an_exempt_line_has_its_cause_and_no_rate_nor_quota():
    line = {
        **VAT21,
        "qualification": "exempt",
        "exempt_reason": "e1",
        "rate": "0.00",
        "quota": 0,
    }
    xml = alta_xml(ticket(tax_breakdown=[line], tax_amount=0, total_amount=1000))
    assert "<sum1:OperacionExenta>E1</sum1:OperacionExenta>" in xml
    assert (
        "CalificacionOperacion" not in xml
        and "TipoImpositivo" not in xml
        and "CuotaRepercutida" not in xml
    )


def test_an_exempt_line_without_a_cause_is_exempt_for_other_reasons():
    line = {
        **VAT21,
        "qualification": "exempt",
        "exempt_reason": "",
        "rate": "0.00",
        "quota": 0,
    }
    assert "<sum1:OperacionExenta>E6</sum1:OperacionExenta>" in alta_xml(
        ticket(tax_breakdown=[line])
    )


def test_reverse_charge_declares_explicit_zeros():
    line = {**VAT21, "qualification": "subject_reverse", "rate": "0.00", "quota": 0}
    xml = alta_xml(ticket(tax_breakdown=[line], tax_amount=0, total_amount=1000))
    assert (
        "<sum1:CalificacionOperacion>S2</sum1:CalificacionOperacion><sum1:TipoImpositivo>0.00</sum1:TipoImpositivo>"
        in xml
    )
    assert "<sum1:CuotaRepercutida>0.00</sum1:CuotaRepercutida>" in xml


@pytest.mark.parametrize(
    ("qualification", "code"), [("not_subject", "N1"), ("not_subject_location", "N2")]
)
def test_a_line_not_subject_carries_no_rate_nor_quota(qualification, code):
    line = {**VAT21, "qualification": qualification, "rate": "0.00", "quota": 0}
    xml = alta_xml(ticket(tax_breakdown=[line], tax_amount=0, total_amount=1000))
    assert f"<sum1:CalificacionOperacion>{code}</sum1:CalificacionOperacion>" in xml
    assert "TipoImpositivo" not in xml and "CuotaRepercutida" not in xml


@pytest.mark.parametrize(("tax", "regime"), [("vat", "08"), ("igic", "20")])
def test_a_regime_located_elsewhere_is_always_n2(tax, regime):
    line = {**VAT21, "tax": tax, "regime": regime}
    assert "<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>" in alta_xml(
        ticket(tax_breakdown=[line])
    )


def test_the_breakdown_is_ordered_by_key_and_the_higher_rate_first():
    lines = [
        {**VAT21, "rate": "10.00", "quota": 100},
        {**VAT21, "tax": "igic", "rate": "7.00", "quota": 70},
        {**VAT21},
    ]
    xml = alta_xml(ticket(tax_breakdown=lines, tax_amount=380, total_amount=3380))
    assert (
        xml.index("21.00")
        < xml.index("10.00")
        < xml.index("<sum1:Impuesto>03</sum1:Impuesto>")
    )


def test_a_breakdown_of_twelve_keys_is_declared_whole():
    lines = [
        {**VAT21, "rate": f"{rate}.00", "quota": rate * 10} for rate in range(1, 13)
    ]
    assert alta_xml(ticket(tax_breakdown=lines)).count("<sum1:DetalleDesglose>") == 12


def test_a_breakdown_of_more_than_twelve_keys_is_refused_never_trimmed():
    # The XSD admits 12 DetalleDesglose: dropping the rest would declare less tax than was charged.
    lines = [
        {**VAT21, "rate": f"{rate}.00", "quota": rate * 10} for rate in range(1, 14)
    ]
    with pytest.raises(envelope.UndeclarableRecord, match="13"):
        alta_xml(ticket(tax_breakdown=lines))


def test_a_breakdown_without_lines_is_refused():
    with pytest.raises(envelope.UndeclarableRecord):
        alta_xml(ticket(tax_breakdown=[]))


def test_the_text_is_escaped():
    xml = alta_xml(ticket(issuer_name="Ana & Co <\"'>", description="a < b"))
    assert (
        "<sum1:NombreRazonEmisor>Ana &amp; Co &lt;&quot;&apos;&gt;</sum1:NombreRazonEmisor>"
        in xml
    )
    assert "<sum1:DescripcionOperacion>a &lt; b</sum1:DescripcionOperacion>" in xml


def test_the_operation_date_goes_only_when_it_differs():
    assert "FechaOperacion" not in alta_xml(ticket(operation_date=DAY))
    xml = alta_xml(ticket(operation_date=dt.date(2026, 10, 13)))
    assert (
        "<sum1:FechaOperacion>13-10-2026</sum1:FechaOperacion><sum1:DescripcionOperacion>"
        in xml
    )


def test_a_simplified_ticket_names_no_recipient():
    assert "Destinatarios" not in alta_xml(ticket())


def test_a_spanish_recipient_is_a_nif_without_its_es_prefix():
    xml = alta_xml(
        ticket(
            invoice_type="F1",
            recipient_name="Talleres SL",
            recipient_tax_id="ESB12345674",
            recipient_country="ES",
        )
    )
    assert (
        "<sum1:Destinatarios><sum1:IDDestinatario><sum1:NombreRazon>Talleres SL</sum1:NombreRazon>"
        "<sum1:NIF>B12345674</sum1:NIF></sum1:IDDestinatario></sum1:Destinatarios><sum1:Desglose>"
    ) in xml


def test_an_eu_vat_number_without_its_prefix_takes_the_countrys():
    xml = alta_xml(
        ticket(
            invoice_type="F1",
            recipient_name="GmbH",
            recipient_tax_id="123456789",
            recipient_country="DE",
        )
    )
    assert (
        "<sum1:IDOtro><sum1:CodigoPais>DE</sum1:CodigoPais><sum1:IDType>02</sum1:IDType><sum1:ID>DE123456789</sum1:ID></sum1:IDOtro>"
        in xml
    )


def test_a_foreign_id_without_a_declared_kind_is_an_id_of_the_country_of_residence():
    xml = alta_xml(
        ticket(
            invoice_type="F1",
            recipient_name="Inc",
            recipient_tax_id="12-345",
            recipient_country="US",
        )
    )
    assert (
        "<sum1:CodigoPais>US</sum1:CodigoPais><sum1:IDType>04</sum1:IDType><sum1:ID>12345</sum1:ID>"
        in xml
    )


def test_without_a_country_a_vat_prefix_decides():
    xml = alta_xml(
        ticket(
            invoice_type="F1", recipient_name="Sarl", recipient_tax_id="FR12345678901"
        )
    )
    assert (
        "<sum1:CodigoPais>FR</sum1:CodigoPais><sum1:IDType>02</sum1:IDType><sum1:ID>FR12345678901</sum1:ID>"
        in xml
    )


def test_a_foreign_id_is_cut_at_twenty_characters():
    xml = alta_xml(
        ticket(
            invoice_type="F1",
            recipient_name="X",
            recipient_tax_id="A" * 30,
            recipient_country="US",
            recipient_id_type="06",
        )
    )
    assert f"<sum1:ID>{'A' * 20}</sum1:ID>" in xml


def test_a_rectifying_invoice_by_differences_names_what_it_rectifies():
    data = ticket(
        invoice_type="R5",
        number="RECT-2026-000001",
        rectification_kind="I",
        rectified=(
            InvoiceRef("B12345674", "TICKET-2026-000001", dt.date(2026, 10, 13)),
        ),
        tax_amount=-210,
        total_amount=-1210,
        tax_breakdown=[{**VAT21, "base": -1000, "quota": -210}],
    )
    xml = alta_xml(data)
    assert (
        "<sum1:TipoFactura>R5</sum1:TipoFactura><sum1:TipoRectificativa>I</sum1:TipoRectificativa>"
        "<sum1:FacturasRectificadas><sum1:IDFacturaRectificada><sum1:IDEmisorFactura>B12345674</sum1:IDEmisorFactura>"
        "<sum1:NumSerieFactura>TICKET-2026-000001</sum1:NumSerieFactura>"
        "<sum1:FechaExpedicionFactura>13-10-2026</sum1:FechaExpedicionFactura></sum1:IDFacturaRectificada>"
        "</sum1:FacturasRectificadas><sum1:DescripcionOperacion>"
    ) in xml
    assert (
        "<sum1:CuotaTotal>-2.10</sum1:CuotaTotal><sum1:ImporteTotal>-12.10</sum1:ImporteTotal>"
        in xml
    )
    assert "ImporteRectificacion" not in xml


def test_a_rectifying_invoice_without_its_kind_is_by_differences():
    xml = alta_xml(ticket(invoice_type="R1", rectification_kind=""))
    assert "<sum1:TipoRectificativa>I</sum1:TipoRectificativa>" in xml


def test_a_rectification_by_substitution_needs_its_rectified_amounts():
    with pytest.raises(envelope.UndeclarableRecord):
        alta_xml(ticket(invoice_type="R1", rectification_kind="S"))
    xml = alta_xml(
        ticket(
            invoice_type="R1",
            rectification_kind="S",
            rectified_base_amount=1000,
            rectified_tax_amount=210,
        )
    )
    assert (
        "<sum1:ImporteRectificacion><sum1:BaseRectificada>10.00</sum1:BaseRectificada>"
        "<sum1:CuotaRectificada>2.10</sum1:CuotaRectificada></sum1:ImporteRectificacion>"
    ) in xml


def test_an_ordinary_invoice_carries_no_rectification_block():
    xml = alta_xml(ticket(invoice_type="F1", rectification_kind="I"))
    assert "TipoRectificativa" not in xml


def test_an_f3_declares_the_ticket_it_replaces():
    data = ticket(
        invoice_type="F3",
        substituted=(
            InvoiceRef("B12345674", "TICKET-2026-000145", dt.date(2026, 6, 8)),
        ),
        recipient_name="Talleres SL",
        recipient_tax_id="B12345674",
    )
    xml = alta_xml(data)
    assert (
        "<sum1:TipoFactura>F3</sum1:TipoFactura><sum1:FacturasSustituidas><sum1:IDFacturaSustituida>"
        "<sum1:IDEmisorFactura>B12345674</sum1:IDEmisorFactura><sum1:NumSerieFactura>TICKET-2026-000145</sum1:NumSerieFactura>"
        "<sum1:FechaExpedicionFactura>08-06-2026</sum1:FechaExpedicionFactura></sum1:IDFacturaSustituida>"
        "</sum1:FacturasSustituidas><sum1:DescripcionOperacion>"
    ) in xml


@pytest.mark.parametrize(
    ("previous_rejection", "expected"),
    [
        # §9.1.3: the initial alta was rejected, so the invoice is not in the AEAT yet.
        ("X", "<sum1:RechazoPrevio>X</sum1:RechazoPrevio>"),
        # The AEAT holds the invoice and a later correction of it was rejected.
        ("S", "<sum1:RechazoPrevio>S</sum1:RechazoPrevio>"),
        # §9.1.2: the usual correction of a record the AEAT holds.
        ("N", ""),
    ],
)
def test_a_correction_says_subsanacion_and_its_previous_rejection(
    previous_rejection, expected
):
    xml = alta_xml(ticket(correction=True, previous_rejection=previous_rejection))
    assert (
        f"<sum1:NombreRazonEmisor>Peluquería Ana SL</sum1:NombreRazonEmisor><sum1:Subsanacion>S</sum1:Subsanacion>{expected}<sum1:TipoFactura>"
        in xml
    )


def test_an_original_alta_says_nothing_of_corrections():
    xml = alta_xml(ticket())
    assert "Subsanacion" not in xml and "RechazoPrevio" not in xml


def test_the_first_record_of_a_chain_says_so():
    assert (
        "<sum1:Encadenamiento><sum1:PrimerRegistro>S</sum1:PrimerRegistro></sum1:Encadenamiento>"
        in alta_xml(ticket())
    )


def test_the_next_record_names_its_previous_one():
    previous = ChainLink(
        "B12345674", "TICKET-2026-000001", dt.date(2026, 10, 13), "B" * 64
    )
    xml = alta_xml(ticket(number="TICKET-2026-000002"), previous)
    assert (
        "<sum1:Encadenamiento><sum1:RegistroAnterior><sum1:IDEmisorFactura>B12345674</sum1:IDEmisorFactura>"
        "<sum1:NumSerieFactura>TICKET-2026-000001</sum1:NumSerieFactura>"
        f"<sum1:FechaExpedicionFactura>13-10-2026</sum1:FechaExpedicionFactura><sum1:Huella>{'B' * 64}</sum1:Huella>"
        "</sum1:RegistroAnterior></sum1:Encadenamiento>"
    ) in xml


def test_an_anulacion_names_the_cancelled_invoice_and_carries_no_amounts():
    data = AnulacionData(
        issuer_nif="B12345674", number="TICKET-2026-000001", issue_date=DAY
    )
    xml = envelope.registro_anulacion(
        data, previous=None, system=SYSTEM, generated_at=TS, fingerprint="C" * 64
    )
    assert xml.startswith(
        "<sum1:RegistroAnulacion><sum1:IDVersion>1.0</sum1:IDVersion><sum1:IDFactura>"
        "<sum1:IDEmisorFacturaAnulada>B12345674</sum1:IDEmisorFacturaAnulada>"
        "<sum1:NumSerieFacturaAnulada>TICKET-2026-000001</sum1:NumSerieFacturaAnulada>"
        "<sum1:FechaExpedicionFacturaAnulada>14-10-2026</sum1:FechaExpedicionFacturaAnulada></sum1:IDFactura>"
        "<sum1:Encadenamiento>"
    )
    assert xml.endswith(
        f"<sum1:TipoHuella>01</sum1:TipoHuella><sum1:Huella>{'C' * 64}</sum1:Huella></sum1:RegistroAnulacion>"
    )
    assert "ImporteTotal" not in xml and "TipoFactura" not in xml


def test_an_anulacion_after_a_rejected_anulacion_says_so():
    # §9.2.2: the invoice is in the AEAT and the earlier anulación of it was rejected.
    data = AnulacionData(
        issuer_nif="B12345674", number="T-1", issue_date=DAY, previous_rejection="S"
    )
    xml = envelope.registro_anulacion(
        data, previous=None, system=SYSTEM, generated_at=TS, fingerprint="C" * 64
    )
    assert (
        "</sum1:IDFactura><sum1:RechazoPrevio>S</sum1:RechazoPrevio><sum1:Encadenamiento>"
        in xml
    )


def test_a_submission_carries_several_records_under_one_header():
    first = alta_xml(ticket())
    second = alta_xml(ticket(number="TICKET-2026-000002"))
    whole = envelope.submission(
        obligado_name="Peluquería Ana SL",
        obligado_nif="B12345674",
        registros=[first, second],
    )
    assert whole.count("<sum:Cabecera>") == 1
    assert whole.count("<sum:RegistroFactura>") == 2
    assert whole.index("TICKET-2026-000001") < whole.index("TICKET-2026-000002")


def test_a_late_submission_declares_the_incidence_after_the_representative():
    whole = envelope.submission(
        obligado_name="Peluquería Ana SL",
        obligado_nif="B12345674",
        registros=[alta_xml(ticket())],
        representative=("ERPLORA CLOUD SL", "B27593136"),
        incident=True,
    )
    assert (
        "<sum:Cabecera><sum1:ObligadoEmision><sum1:NombreRazon>Peluquería Ana SL</sum1:NombreRazon>"
        "<sum1:NIF>B12345674</sum1:NIF></sum1:ObligadoEmision>"
        "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon><sum1:NIF>B27593136</sum1:NIF></sum1:Representante>"
        "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia></sum1:RemisionVoluntaria></sum:Cabecera>"
    ) in whole


def test_the_obligado_never_represents_itself():
    whole = envelope.submission(
        obligado_name="ERPLORA CLOUD SL",
        obligado_nif="B27593136",
        registros=[alta_xml(ticket())],
        representative=("ERPLORA CLOUD SL", " b27593136 "),
    )
    assert "Representante" not in whole


def test_a_submission_needs_at_least_one_record_and_at_most_a_thousand():
    with pytest.raises(envelope.UndeclarableRecord):
        envelope.submission(obligado_name="A", obligado_nif="B12345674", registros=[])
    with pytest.raises(envelope.UndeclarableRecord):
        envelope.submission(
            obligado_name="A", obligado_nif="B12345674", registros=["<x/>"] * 1001
        )


def test_the_registro_is_the_one_inside_a_single_record_envelope():
    registro = alta_xml(ticket())
    whole = envelope.submission(
        obligado_name="Peluquería Ana SL",
        obligado_nif="B12345674",
        registros=[registro],
    )
    assert envelope.registros_of(whole) == [registro]


# The query (VERIFACTU-F27, F28)


def test_the_query_names_the_obligado_and_the_period():
    xml = envelope.query(
        obligado_nif="B12345674", obligado_name="Peluquería Ana SL", year=2026, month=8
    )
    assert (
        "<con:Cabecera><sum1:IDVersion>1.0</sum1:IDVersion><sum1:ObligadoEmision>"
        "<sum1:NombreRazon>Peluquería Ana SL</sum1:NombreRazon><sum1:NIF>B12345674</sum1:NIF>"
        "</sum1:ObligadoEmision></con:Cabecera><con:FiltroConsulta><con:PeriodoImputacion>"
        "<sum1:Ejercicio>2026</sum1:Ejercicio><sum1:Periodo>08</sum1:Periodo></con:PeriodoImputacion>"
    ) in xml
    assert "IndicadorRepresentante" not in xml


def test_a_query_through_erplora_raises_the_representative_flag():
    xml = envelope.query(
        obligado_nif="B12345674",
        obligado_name="Ana",
        year=2026,
        month=8,
        represented=True,
    )
    assert (
        "</sum1:ObligadoEmision><sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante></con:Cabecera>"
        in xml
    )


def test_a_query_continues_after_the_last_record_of_the_previous_page():
    # §6.4.3: ClavePaginacion names the last record the previous answer returned.
    xml = envelope.query(
        obligado_nif="B12345674",
        obligado_name="Ana",
        year=2026,
        month=8,
        after=envelope.InvoiceRef("B12345674", "TICKET-2026-009999", DAY),
    )
    assert (
        "</con:PeriodoImputacion><con:ClavePaginacion><sum1:IDEmisorFactura>B12345674</sum1:IDEmisorFactura>"
        "<sum1:NumSerieFactura>TICKET-2026-009999</sum1:NumSerieFactura>"
        f"<sum1:FechaExpedicionFactura>{DAY:%d-%m-%Y}</sum1:FechaExpedicionFactura></con:ClavePaginacion>"
        "</con:FiltroConsulta>"
    ) in xml


def test_a_query_needs_the_name_of_the_obligado():
    with pytest.raises(envelope.UndeclarableRecord):
        envelope.query(obligado_nif="B12345674", obligado_name=" ", year=2026, month=8)
