"""The XML VeriFactu speaks (VERIFACTU-F13–F15, F24, F27, F30): a record (``RegistroAlta`` /
``RegistroAnulacion``), the submission that carries records (``RegFactuSistemaFacturacion`` in its SOAP
envelope) and the query (``ConsultaFactuSistemaFacturacion``).

Pure functions, no ORM. A port, byte for byte, of the current engine's ``aeat::build_soap`` (hub
``crates/plugins/verifactu/src/aeat.rs``), whose envelopes the AEAT's preproduction accepted: the 19 kept in
``tests/fixtures/*_sent_*.xml`` are rebuilt identical by ``tests/test_envelope.py``. Added here: the operation
date (``FechaOperacion``, when it is not the issue date), ``Subsanacion`` / ``RechazoPrevio`` (VERIFACTU-F24)
and a submission of several records under one header (up to 1,000 of one obligado).

Amounts arrive in cents with their sign and become euros only here; the breakdown is Invoicing's
``tax_breakdown`` (one entry per fiscal key). Every element goes in the order of its ``xs:sequence`` of
``SuministroInformacion.xsd``; ``xsd.py`` checks the result against the real schemas.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from apps.verifactu.chain import format_amount, format_date, format_rate
from apps.verifactu.producer import SystemInfo

__all__ = [
    "AltaData",
    "AnulacionData",
    "ChainLink",
    "InvoiceRef",
    "SystemInfo",
    "UndeclarableRecord",
    "query",
    "registro_alta",
    "registro_anulacion",
    "registros_of",
    "submission",
]

SUM = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd"
SUM1 = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd"
CON = "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/ConsultaLR.xsd"
SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"

RECTIFYING_TYPES = ("R1", "R2", "R3", "R4", "R5")
BY_SUBSTITUTION = "S"
BY_DIFFERENCES = "I"
#: ``DetalleDesglose`` is ``maxOccurs="12"``; ``RegistroFactura`` admits 1,000 per submission.
MAX_BREAKDOWN_LINES = 12
MAX_RECORDS = 1000
#: ``ID`` of ``IDOtro`` is ``TextMax20Type``.
ID_OTRO_MAX_LENGTH = 20
NIF_IVA = "02"
ID_IN_COUNTRY_OF_RESIDENCE = "04"
FOREIGN_ID_TYPES = ("02", "03", "04", "05", "06", "07")
NORTHERN_IRELAND_VAT_PREFIX = "XI"
#: The VAT prefixes of the EU member states but Spain → their ISO code (only Greece differs).
EU_VAT_PREFIXES = {
    "AT": "AT",
    "BE": "BE",
    "BG": "BG",
    "CY": "CY",
    "CZ": "CZ",
    "DE": "DE",
    "DK": "DK",
    "EE": "EE",
    "EL": "GR",
    "FI": "FI",
    "FR": "FR",
    "HR": "HR",
    "HU": "HU",
    "IE": "IE",
    "IT": "IT",
    "LT": "LT",
    "LU": "LU",
    "LV": "LV",
    "MT": "MT",
    "NL": "NL",
    "PL": "PL",
    "PT": "PT",
    "RO": "RO",
    "SE": "SE",
    "SI": "SI",
    "SK": "SK",
}
#: ``Impuesto`` (L1): what is not recognised is VAT, the AEAT's own default.
TAX_CODES = {
    "igic": "03",
    "03": "03",
    "ipsi": "02",
    "02": "02",
    "other": "05",
    "otros": "05",
    "05": "05",
}
QUALIFICATION_CODES = {
    "subject_reverse": "S2",
    "not_subject": "N1",
    "not_subject_location": "N2",
}
_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]")


class UndeclarableRecord(ValueError):
    """What cannot be declared to the AEAT: it stops here, before a chain number or the network."""


@dataclass(frozen=True)
class InvoiceRef:
    """An invoice another one rectifies or replaces (``IDFacturaARType``)."""

    issuer_nif: str
    number: str
    issue_date: object


@dataclass(frozen=True)
class ChainLink:
    """The previous record of the chain, as ``Encadenamiento/RegistroAnterior`` names it."""

    issuer_nif: str
    number: str
    issue_date: object
    fingerprint: str


@dataclass(frozen=True)
class AltaData:
    """What an alta declares of an issued invoice (amounts in cents, with their sign)."""

    issuer_nif: str
    issuer_name: str
    number: str
    issue_date: object
    invoice_type: str
    description: str
    tax_breakdown: list
    tax_amount: int
    total_amount: int
    operation_date: object = None
    rectification_kind: str = ""
    rectified: tuple = ()
    substituted: tuple = ()
    rectified_base_amount: int | None = None
    rectified_tax_amount: int | None = None
    recipient_name: str = ""
    recipient_tax_id: str = ""
    recipient_country: str = ""
    recipient_id_type: str = ""
    correction: bool = False
    previous_rejection: str = ""


@dataclass(frozen=True)
class AnulacionData:
    """What an anulación declares: the invoice it cancels."""

    issuer_nif: str
    number: str
    issue_date: object
    previous_rejection: str = ""


def _esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _element(name: str, value: object) -> str:
    return f"<sum1:{name}>{_esc(value)}</sum1:{name}>"


# The breakdown


@dataclass(frozen=True)
class _Detail:
    tax: str
    regime: str
    qualification: str  # S1, S2, N1, N2 or "" (exempt)
    exempt: str  # E1…E8 or ""
    rate: Decimal
    base: int
    quota: int
    surcharge_rate: Decimal
    surcharge_quota: int

    @property
    def carries_amounts(self) -> bool:
        # Exempt (§15.5) and N1/N2 (error 1237) carry neither rate nor quota; S2 carries explicit zeros.
        return not self.exempt and self.qualification not in ("N1", "N2")

    @property
    def has_surcharge(self) -> bool:
        return self.surcharge_rate != 0 or self.surcharge_quota != 0

    def render(self) -> str:
        out = [_element("Impuesto", self.tax), _element("ClaveRegimen", self.regime)]
        out.append(
            _element("OperacionExenta", self.exempt)
            if self.exempt
            else _element("CalificacionOperacion", self.qualification)
        )
        if self.carries_amounts:
            out.append(_element("TipoImpositivo", format_rate(self.rate)))
        out.append(_element("BaseImponibleOimporteNoSujeto", format_amount(self.base)))
        if self.carries_amounts:
            out.append(_element("CuotaRepercutida", format_amount(self.quota)))
            if self.has_surcharge:
                out.append(
                    _element(
                        "TipoRecargoEquivalencia", format_rate(self.surcharge_rate)
                    )
                )
                out.append(
                    _element(
                        "CuotaRecargoEquivalencia", format_amount(self.surcharge_quota)
                    )
                )
        return f"<sum1:DetalleDesglose>{''.join(out)}</sum1:DetalleDesglose>"


def _detail(entry: dict) -> _Detail:
    try:
        tax = TAX_CODES.get(str(entry.get("tax", "")).strip().lower(), "01")
        regime = str(entry.get("regime") or "").strip() or "01"
        qualification_name = (
            str(entry.get("qualification") or "subject").strip().lower()
        )
        exempt = ""
        qualification = QUALIFICATION_CODES.get(qualification_name, "S1")
        if qualification_name == "exempt":
            qualification = ""
            exempt = str(entry.get("exempt_reason") or "").strip().upper() or "E6"
        # §15.6.6: a regime located in the Canaries, Ceuta or Melilla (08), or IGIC's 20, is always N2.
        if qualification and (regime == "08" or (tax == "03" and regime == "20")):
            qualification = "N2"
        return _Detail(
            tax=tax,
            regime=regime,
            qualification=qualification,
            exempt=exempt,
            rate=Decimal(str(entry.get("rate") or "0")),
            base=int(entry["base"]),
            quota=int(entry.get("quota") or 0),
            surcharge_rate=Decimal(str(entry.get("surcharge_rate") or "0")),
            surcharge_quota=int(entry.get("surcharge_quota") or 0),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise UndeclarableRecord(
            f"A breakdown entry cannot be read: {entry!r} ({error})."
        ) from None


def _desglose(entries: list) -> str:
    details = [_detail(entry) for entry in entries if isinstance(entry, dict)]
    if not details:
        raise UndeclarableRecord(
            "The breakdown has no line: the AEAT admits no empty Desglose."
        )
    if len(details) > MAX_BREAKDOWN_LINES:
        # Never trimmed: dropping a line would declare less than was charged.
        raise UndeclarableRecord(
            f"The breakdown has {len(details)} lines: the AEAT admits {MAX_BREAKDOWN_LINES}."
        )
    # Stable order: the XML never depends on how the producer built the list; the higher rate first.
    details.sort(key=lambda d: (d.tax, d.regime, d.exempt, d.qualification, -d.rate))
    return "".join(detail.render() for detail in details)


# The recipient


def _vat_country(compact: str) -> str | None:
    prefix = compact[:2]
    if prefix == NORTHERN_IRELAND_VAT_PREFIX:
        return "GB"
    return EU_VAT_PREFIXES.get(prefix)


def _id_otro(country: str, kind: str, number: str) -> str:
    return (
        f"<sum1:IDOtro>{_element('CodigoPais', country)}{_element('IDType', kind)}"
        f"{_element('ID', number[:ID_OTRO_MAX_LENGTH])}</sum1:IDOtro>"
    )


def _recipient_identity(tax_id: str, country: str, id_type: str) -> str:
    """``NIF`` for a Spanish recipient, ``IDOtro`` for anyone else (hub#1965, hub#1967)."""
    compact = _ALPHANUMERIC.sub("", tax_id).upper()
    country = country.strip().upper()
    declared = id_type.strip() if id_type.strip() in FOREIGN_ID_TYPES else ""
    without_es = (
        compact[2:] if compact.startswith("ES") and len(compact) == 11 else compact
    )
    if not country:
        if without_es != compact:
            return _element("NIF", without_es)
        iso = _vat_country(compact)
        if iso and len(compact) > 2:
            return _id_otro(iso, NIF_IVA, compact)
        return _element("NIF", tax_id)
    if country == "ES":
        return _element("NIF", without_es)
    if declared and declared != NIF_IVA:
        return _id_otro(country, declared, compact)
    prefix = next((vat for vat, iso in EU_VAT_PREFIXES.items() if iso == country), None)
    if (
        prefix is None
        and country == "GB"
        and compact.startswith(NORTHERN_IRELAND_VAT_PREFIX)
    ):
        prefix = NORTHERN_IRELAND_VAT_PREFIX
    if prefix is not None:
        return _id_otro(
            country,
            NIF_IVA,
            compact if compact.startswith(prefix) else f"{prefix}{compact}",
        )
    return _id_otro(country, declared or ID_IN_COUNTRY_OF_RESIDENCE, compact)


def _destinatarios(data: AltaData) -> str:
    if not data.recipient_tax_id.strip():
        return ""
    name = data.recipient_name or data.recipient_tax_id
    identity = _recipient_identity(
        data.recipient_tax_id, data.recipient_country, data.recipient_id_type
    )
    return (
        f"<sum1:Destinatarios><sum1:IDDestinatario>{_element('NombreRazon', name)}{identity}"
        "</sum1:IDDestinatario></sum1:Destinatarios>"
    )


# The rectification and substitution blocks


def _refs(block: str, item: str, refs: tuple) -> str:
    if not refs:
        return ""
    inner = "".join(
        f"<sum1:{item}>{_element('IDEmisorFactura', ref.issuer_nif)}{_element('NumSerieFactura', ref.number)}"
        f"{_element('FechaExpedicionFactura', format_date(ref.issue_date))}</sum1:{item}>"
        for ref in refs
    )
    return f"<sum1:{block}>{inner}</sum1:{block}>"


def _rectification(data: AltaData) -> str:
    if data.invoice_type not in RECTIFYING_TYPES:
        return ""
    kind = data.rectification_kind or (
        BY_SUBSTITUTION if data.rectified_base_amount is not None else BY_DIFFERENCES
    )
    if kind not in (BY_SUBSTITUTION, BY_DIFFERENCES):
        raise UndeclarableRecord(f"TipoRectificativa {kind!r} is neither S nor I.")
    out = _element("TipoRectificativa", kind) + _refs(
        "FacturasRectificadas", "IDFacturaRectificada", data.rectified
    )
    return out


def _amounts_rectified(data: AltaData) -> str:
    """``ImporteRectificacion``: only a rectification by substitution, and never with invented zeros."""
    if (
        data.invoice_type not in RECTIFYING_TYPES
        or (data.rectification_kind or "") != BY_SUBSTITUTION
    ):
        return ""
    if data.rectified_base_amount is None or data.rectified_tax_amount is None:
        raise UndeclarableRecord(
            "A rectification by substitution needs the rectified base and quota (ImporteRectificacion)."
        )
    return (
        "<sum1:ImporteRectificacion>"
        f"{_element('BaseRectificada', format_amount(data.rectified_base_amount))}"
        f"{_element('CuotaRectificada', format_amount(data.rectified_tax_amount))}"
        "</sum1:ImporteRectificacion>"
    )


# The chain and the system


def _encadenamiento(previous: ChainLink | None) -> str:
    if previous is None:
        return "<sum1:Encadenamiento><sum1:PrimerRegistro>S</sum1:PrimerRegistro></sum1:Encadenamiento>"
    return (
        "<sum1:Encadenamiento><sum1:RegistroAnterior>"
        f"{_element('IDEmisorFactura', previous.issuer_nif)}{_element('NumSerieFactura', previous.number)}"
        f"{_element('FechaExpedicionFactura', format_date(previous.issue_date))}"
        f"{_element('Huella', previous.fingerprint)}"
        "</sum1:RegistroAnterior></sum1:Encadenamiento>"
    )


def _sistema(system: SystemInfo) -> str:
    return (
        "<sum1:SistemaInformatico>"
        f"{_element('NombreRazon', system.name)}{_element('NIF', system.nif)}"
        f"{_element('NombreSistemaInformatico', system.system_name)}"
        f"{_element('IdSistemaInformatico', system.system_id)}{_element('Version', system.version)}"
        f"{_element('NumeroInstalacion', system.installation)}"
        f"{_element('TipoUsoPosibleSoloVerifactu', system.only_verifactu)}"
        f"{_element('TipoUsoPosibleMultiOT', system.multi_ot)}"
        f"{_element('IndicadorMultiplesOT', system.multiple_ot)}"
        "</sum1:SistemaInformatico>"
    )


def _tail(
    previous: ChainLink | None, system: SystemInfo, generated_at: str, fingerprint: str
) -> str:
    return (
        f"{_encadenamiento(previous)}{_sistema(system)}"
        f"{_element('FechaHoraHusoGenRegistro', generated_at)}"
        f"{_element('TipoHuella', '01')}{_element('Huella', fingerprint)}"
    )


# Records


def registro_alta(
    data: AltaData,
    *,
    previous: ChainLink | None,
    system: SystemInfo,
    generated_at: str,
    fingerprint: str,
) -> str:
    """The ``RegistroAlta`` of an issued invoice."""
    correction = ""
    if data.correction:
        correction = _element("Subsanacion", "S")
        # S: the AEAT holds the invoice and a later correction was rejected; X: it holds none (§9.1.3).
        if data.previous_rejection in ("S", "X"):
            correction += _element("RechazoPrevio", data.previous_rejection)
    operation_date = ""
    if data.operation_date is not None and data.operation_date != data.issue_date:
        operation_date = _element("FechaOperacion", format_date(data.operation_date))
    return (
        "<sum1:RegistroAlta><sum1:IDVersion>1.0</sum1:IDVersion><sum1:IDFactura>"
        f"{_element('IDEmisorFactura', data.issuer_nif)}{_element('NumSerieFactura', data.number)}"
        f"{_element('FechaExpedicionFactura', format_date(data.issue_date))}</sum1:IDFactura>"
        f"{_element('NombreRazonEmisor', data.issuer_name)}{correction}"
        f"{_element('TipoFactura', data.invoice_type)}"
        f"{_rectification(data)}"
        f"{_refs('FacturasSustituidas', 'IDFacturaSustituida', data.substituted)}"
        f"{_amounts_rectified(data)}{operation_date}"
        f"{_element('DescripcionOperacion', data.description)}"
        f"{_destinatarios(data)}"
        f"<sum1:Desglose>{_desglose(data.tax_breakdown)}</sum1:Desglose>"
        f"{_element('CuotaTotal', format_amount(data.tax_amount))}"
        f"{_element('ImporteTotal', format_amount(data.total_amount))}"
        f"{_tail(previous, system, generated_at, fingerprint)}"
        "</sum1:RegistroAlta>"
    )


def registro_anulacion(
    data: AnulacionData,
    *,
    previous: ChainLink | None,
    system: SystemInfo,
    generated_at: str,
    fingerprint: str,
) -> str:
    """The ``RegistroAnulacion`` of an invoice issued by error."""
    rejection = _element("RechazoPrevio", "S") if data.previous_rejection == "S" else ""
    return (
        "<sum1:RegistroAnulacion><sum1:IDVersion>1.0</sum1:IDVersion><sum1:IDFactura>"
        f"{_element('IDEmisorFacturaAnulada', data.issuer_nif)}"
        f"{_element('NumSerieFacturaAnulada', data.number)}"
        f"{_element('FechaExpedicionFacturaAnulada', format_date(data.issue_date))}</sum1:IDFactura>"
        f"{rejection}{_tail(previous, system, generated_at, fingerprint)}"
        "</sum1:RegistroAnulacion>"
    )


# Submissions and queries


def submission(
    *,
    obligado_name: str,
    obligado_nif: str,
    registros: list[str],
    representative: tuple[str, str] | None = None,
    incident: bool = False,
) -> str:
    """The SOAP envelope of one submission: one header, then each record in chain order.

    ``representative`` = (name, NIF) of whoever presents (ERPlora with its seal) when it is not the obligado;
    ``incident`` declares a late submission (``RemisionVoluntaria/Incidencia = S``). Neither enters a
    fingerprint: the header is the envelope's, not a record's.
    """
    if not registros:
        raise UndeclarableRecord("A submission carries at least one record.")
    if len(registros) > MAX_RECORDS:
        raise UndeclarableRecord(f"A submission carries at most {MAX_RECORDS} records.")
    header = (
        f"<sum1:ObligadoEmision>{_element('NombreRazon', obligado_name)}{_element('NIF', obligado_nif)}"
        "</sum1:ObligadoEmision>"
    )
    if representative is not None:
        name, nif = (part.strip() for part in representative)
        if name and nif and nif.upper() != obligado_nif.strip().upper():
            header += f"<sum1:Representante>{_element('NombreRazon', name)}{_element('NIF', nif)}</sum1:Representante>"
    if incident:
        header += "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia></sum1:RemisionVoluntaria>"
    body = "".join(
        f"<sum:RegistroFactura>{registro}</sum:RegistroFactura>"
        for registro in registros
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{SOAPENV}" xmlns:sum="{SUM}" xmlns:sum1="{SUM1}">'
        "<soapenv:Header/><soapenv:Body><sum:RegFactuSistemaFacturacion>"
        f"<sum:Cabecera>{header}</sum:Cabecera>{body}"
        "</sum:RegFactuSistemaFacturacion></soapenv:Body></soapenv:Envelope>"
    )


_REGISTRO = re.compile(r"<sum:RegistroFactura>(.*?)</sum:RegistroFactura>", re.DOTALL)


def registros_of(whole: str) -> list[str]:
    """The records a submission built by :func:`submission` carries, in order."""
    return _REGISTRO.findall(whole)


def _page_key(after: InvoiceRef | None) -> str:
    if after is None:
        return ""
    return (
        f"<con:ClavePaginacion>{_element('IDEmisorFactura', after.issuer_nif)}"
        f"{_element('NumSerieFactura', after.number)}"
        f"{_element('FechaExpedicionFactura', format_date(after.issue_date))}</con:ClavePaginacion>"
    )


def query(
    *,
    obligado_nif: str,
    obligado_name: str,
    year: int,
    month: int,
    represented: bool = False,
    after: InvoiceRef | None = None,
) -> str:
    """``ConsultaFactuSistemaFacturacion`` of one obligado and month (``Periodo`` is mandatory).

    Through ERPlora (``represented``) the query raises ``IndicadorRepresentante``: unlike the alta, its header
    has no ``Representante`` block, only the flag (AEAT fault 4112 otherwise). ``after``: the next page, after
    the record the previous answer named in its ``ClavePaginacion`` (§6.4.3).
    """
    if not obligado_nif.strip():
        raise UndeclarableRecord("The query needs the obligado's NIF.")
    if not obligado_name.strip():
        raise UndeclarableRecord(
            "The query needs the obligado's name (ObligadoEmisionConsultaType)."
        )
    flag = (
        "<sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante>"
        if represented
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{SOAPENV}" xmlns:con="{CON}" xmlns:sum1="{SUM1}">'
        "<soapenv:Header/><soapenv:Body><con:ConsultaFactuSistemaFacturacion>"
        "<con:Cabecera><sum1:IDVersion>1.0</sum1:IDVersion><sum1:ObligadoEmision>"
        f"{_element('NombreRazon', obligado_name)}{_element('NIF', obligado_nif)}"
        f"</sum1:ObligadoEmision>{flag}</con:Cabecera>"
        "<con:FiltroConsulta><con:PeriodoImputacion>"
        f"{_element('Ejercicio', f'{year:04d}')}{_element('Periodo', f'{month:02d}')}"
        f"</con:PeriodoImputacion>{_page_key(after)}</con:FiltroConsulta>"
        "</con:ConsultaFactuSistemaFacturacion></soapenv:Body></soapenv:Envelope>"
    )
