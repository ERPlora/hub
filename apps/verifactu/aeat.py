"""What the AEAT answers (VERIFACTU-F15, F27, F28): a submission's answer, line by line, and a query's records.

Pure: no ORM. Parsed by structure (``xml.etree``) and by local names, because the AEAT's prefixes vary
(``tikR:``, ``tik:``, ``tikLRRC:``). Ported from the current engine's ``aeat::parse_response``,
``classify``, ``parse_consult_response`` and ``pick_latest_record`` (hub ``crates/plugins/verifactu/src/aeat.rs``),
with what preproduction taught it:

- ``AceptadoConErrores`` is **registered**: never sent again (the AEAT would answer «duplicate»); its code is kept.
- A ``3000`` duplicate carries the original's state in ``RegistroDuplicado``: a record the AEAT already holds as
  ``Correcta`` or ``AceptadaConErrores`` is that record accepted (the old engine marked it rejected and broke the
  chain that followed).
- A SOAP fault refuses the whole SUBMISSION, not its records (the AEAT evaluated none); 4102 (schema), 4104
  (header) and 4116 (the obligado) are permanent (sending it again unchanged will not help), any other is to retry.
- A query that the AEAT refuses is an error, never «no records» (that reading breaks the chain's recovery), and
  the latest record is the one generated last, never the first or the last of the list.
- A record of the queue is in the AEAT when its query returns it with the same fingerprint (``held_as``): the
  number alone could be an earlier record of the same invoice.
- A query answers at most 10,000 records (§6.4.3): ``IndicadorPaginacion`` S says more follow, after the record
  its ``ClavePaginacion`` names.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from apps.verifactu.chain import parse_date
from apps.verifactu.envelope import InvoiceRef

ACCEPTED = "accepted"
ACCEPTED_WITH_ERRORS = "accepted_with_errors"
REJECTED = "rejected"
DUPLICATE = "3000"
PERMANENT_FAULTS = frozenset({"4102", "4104", "4116"})
_FAULT_CODE = re.compile(r"Codigo\[(\d+)\]")


class UnreadableAnswer(ValueError):
    """The body is no answer of the AEAT (a maintenance page, an empty body, another document)."""


class AeatFault(ValueError):
    """The AEAT refused the whole request with a SOAP fault."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LineVerdict:
    """The AEAT's verdict on one record of a submission."""

    issuer_nif: str
    number: str
    issue_date: dt.date | None
    operation: str
    status: str
    code: str = ""
    message: str = ""
    duplicate: bool = False


@dataclass(frozen=True)
class SubmissionAnswer:
    csv: str = ""
    submission_state: str = ""
    wait_seconds: int | None = None
    lines: list[LineVerdict] = field(default_factory=list)
    fault_code: str = ""
    fault_message: str = ""

    @property
    def permanent_fault(self) -> bool:
        return self.fault_code in PERMANENT_FAULTS


@dataclass(frozen=True)
class QueriedRecord:
    """A record as the AEAT's query returns it."""

    issuer_nif: str
    number: str
    issue_date: dt.date | None
    fingerprint: str
    state: str
    generated_at: dt.datetime | None
    csv: str = ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in node if _local(child.tag) == name), None)


def _text(node: ET.Element | None, *path: str) -> str:
    for name in path:
        if node is None:
            return ""
        node = _child(node, name)
    return (node.text or "").strip() if node is not None else ""


def _parse(body: str) -> ET.Element:
    if not body or not body.strip():
        raise UnreadableAnswer("The AEAT's answer is empty.")
    try:
        return ET.fromstring(body.encode("utf-8"))
    except ET.ParseError as error:
        raise UnreadableAnswer(f"The AEAT's answer is not XML: {error}.") from None


def _find(root: ET.Element, name: str) -> ET.Element | None:
    return next((node for node in root.iter() if _local(node.tag) == name), None)


def _fault(root: ET.Element) -> tuple[str, str] | None:
    fault = _find(root, "Fault")
    if fault is None:
        return None
    message = _text(fault, "faultstring")
    found = _FAULT_CODE.search(message)
    return (found.group(1) if found else _text(fault, "faultcode")), message


def _date(text: str) -> dt.date | None:
    try:
        return parse_date(text) if text else None
    except ValueError:
        return None


def _line(node: ET.Element) -> LineVerdict:
    state = _text(node, "EstadoRegistro")
    code = _text(node, "CodigoErrorRegistro")
    message = _text(node, "DescripcionErrorRegistro")
    duplicate = False
    if state == "Correcto":
        status = ACCEPTED
    elif state == "AceptadoConErrores":
        status = ACCEPTED_WITH_ERRORS
    else:
        status = REJECTED
        original = _child(node, "RegistroDuplicado")
        if code == DUPLICATE and original is not None:
            held = _text(original, "EstadoRegistroDuplicado")
            if held in ("Correcta", "AceptadaConErrores"):
                duplicate = True
                status = ACCEPTED if held == "Correcta" else ACCEPTED_WITH_ERRORS
                code = _text(original, "CodigoErrorRegistro")
                message = _text(original, "DescripcionErrorRegistro")
    return LineVerdict(
        issuer_nif=_text(node, "IDFactura", "IDEmisorFactura"),
        number=_text(node, "IDFactura", "NumSerieFactura"),
        issue_date=_date(_text(node, "IDFactura", "FechaExpedicionFactura")),
        operation=_text(node, "Operacion", "TipoOperacion"),
        status=status,
        code=code,
        message=message,
        duplicate=duplicate,
    )


def parse_submission(body: str) -> SubmissionAnswer:
    """The answer to a ``RegFactuSistemaFacturacion``: its header and one verdict per record."""
    root = _parse(body)
    fault = _fault(root)
    if fault is not None:
        return SubmissionAnswer(fault_code=fault[0], fault_message=fault[1])
    answer = _find(root, "RespuestaRegFactuSistemaFacturacion")
    if answer is None:
        raise UnreadableAnswer("The body is no answer to a VeriFactu submission.")
    wait = _text(answer, "TiempoEsperaEnvio")
    return SubmissionAnswer(
        csv=_text(answer, "CSV"),
        submission_state=_text(answer, "EstadoEnvio"),
        wait_seconds=int(wait) if wait.isdigit() else None,
        lines=[_line(node) for node in answer if _local(node.tag) == "RespuestaLinea"],
    )


def _timestamp(text: str) -> dt.datetime | None:
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


@dataclass(frozen=True)
class QueryPage:
    """One answer of a query: its records and, when more follow, the record to ask after (``ClavePaginacion``)."""

    records: list[QueriedRecord]
    more: bool = False
    after: InvoiceRef | None = None


def parse_query(body: str) -> QueryPage:
    """The page a ``ConsultaFactuSistemaFacturacion`` returns; ``AeatFault`` if the AEAT refused it."""
    root = _parse(body)
    fault = _fault(root)
    if fault is not None:
        raise AeatFault(*fault)
    answer = _find(root, "RespuestaConsultaFactuSistemaFacturacion")
    if answer is None:
        raise UnreadableAnswer("The body is no answer to a VeriFactu query.")
    records = []
    for node in answer:
        if _local(node.tag) != "RegistroRespuestaConsultaFactuSistemaFacturacion":
            continue
        records.append(
            QueriedRecord(
                issuer_nif=_text(node, "IDFactura", "IDEmisorFactura"),
                number=_text(node, "IDFactura", "NumSerieFactura"),
                issue_date=_date(_text(node, "IDFactura", "FechaExpedicionFactura")),
                # Directly under DatosRegistroFacturacion: Encadenamiento/RegistroAnterior repeats the tag
                # with the PREVIOUS record's fingerprint.
                fingerprint=_text(node, "DatosRegistroFacturacion", "Huella"),
                state=_text(node, "EstadoRegistro", "EstadoRegistro"),
                generated_at=_timestamp(
                    _text(node, "DatosRegistroFacturacion", "FechaHoraHusoGenRegistro")
                ),
                csv=_text(node, "CSV"),
            )
        )
    if _text(answer, "IndicadorPaginacion") != "S":
        return QueryPage(records)
    key = _child(answer, "ClavePaginacion")
    after = InvoiceRef(
        _text(key, "IDEmisorFactura"),
        _text(key, "NumSerieFactura"),
        _date(_text(key, "FechaExpedicionFactura")),
    )
    if not (after.issuer_nif and after.number and after.issue_date):
        raise UnreadableAnswer("More records follow but the answer has no ClavePaginacion to ask for them.")
    return QueryPage(records, more=True, after=after)


def latest(records: list[QueriedRecord]) -> QueriedRecord | None:
    """The record generated last (the chain's order); a record without fingerprint or time anchors nothing."""
    candidates = [
        record
        for record in records
        if record.fingerprint and record.generated_at is not None
    ]
    return max(candidates, key=lambda record: record.generated_at, default=None)


#: How the AEAT's query names a record it registered (``EstadoRegistro`` of RespuestaConsultaLR.xsd), as our status.
HELD_STATES = {
    "Correcto": ACCEPTED,
    "AceptadoConErrores": ACCEPTED_WITH_ERRORS,
    "Anulado": ACCEPTED,
}


def held_as(
    records: list[QueriedRecord], issuer_nif: str, number: str, fingerprint: str
) -> str | None:
    """Our status for the record the AEAT holds with this issuer, number and fingerprint; ``None`` when it holds no
    such record. Only the fingerprint tells that it is THIS record: another one of the same invoice (a correction
    it has not registered yet) is not, and a state it never documented is never taken as registered."""
    wanted = fingerprint.strip().upper()
    if not wanted:
        return None
    for record in records:
        if (
            record.issuer_nif.upper() == issuer_nif.upper()
            and record.number == number
            and record.fingerprint.strip().upper() == wanted
        ):
            return HELD_STATES.get(record.state)
    return None
