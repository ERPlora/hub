"""Validation against the AEAT's real schemas (VERIFACTU-F13, F15).

``xmlschema`` (maintained since 2017, 45 contributors) reads ``xsd/SuministroLR.xsd``, which imports
``SuministroInformacion.xsd``, which imports the W3C XML signature schema by its public URL: that URL is mapped
to the local copy and the loader runs in ``sandbox`` mode, so validating never reaches the network. The schema
is loaded once per process (it takes about a tenth of a second).

What is validated is the ``RegFactuSistemaFacturacion`` inside the SOAP envelope (the envelope itself is SOAP's,
not the AEAT's schema), and a query's ``ConsultaFactuSistemaFacturacion`` against ``xsd/ConsultaLR.xsd``. Pure:
no ORM.
"""

import re
from functools import cache
from pathlib import Path
from xml.etree import ElementTree as ET

import xmlschema

from apps.verifactu import envelope

SCHEMAS_DIR = Path(__file__).resolve().parent / "xsd"
SIGNATURE_URL = "http://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd"
SIGNATURE_FILE = SCHEMAS_DIR / "xmldsig-core-schema.xsd"
#: Errors are cut to this many characters: enough to name the element and the reason.
MESSAGE_MAX_LENGTH = 600
_NAMESPACE = re.compile(r"\{[^}]*\}")


class SchemaError(ValueError):
    """The document does not validate against the AEAT's schemas."""


def _local(uri: str) -> str:
    return SIGNATURE_FILE.as_uri() if uri == SIGNATURE_URL else uri


@cache
def schema() -> xmlschema.XMLSchema:
    """The AEAT's ``SuministroLR.xsd`` with its imports, all from disk."""
    return xmlschema.XMLSchema(
        str(SCHEMAS_DIR / "SuministroLR.xsd"),
        base_url=str(SCHEMAS_DIR),
        allow="sandbox",
        uri_mapper=_local,
    )


@cache
def query_schema() -> xmlschema.XMLSchema:
    """The AEAT's ``ConsultaLR.xsd`` with its imports, all from disk."""
    return xmlschema.XMLSchema(
        str(SCHEMAS_DIR / "ConsultaLR.xsd"),
        base_url=str(SCHEMAS_DIR),
        allow="sandbox",
        uri_mapper=_local,
    )


def _summary(error: xmlschema.XMLSchemaValidationError) -> str:
    """``/RegFactuSistemaFacturacion/…/Element: reason``, without the namespaces' long URIs."""
    path = _NAMESPACE.sub("", error.path or "")
    reason = _NAMESPACE.sub("", error.reason or str(error))
    return f"{path}: {reason}"[:MESSAGE_MAX_LENGTH]


def _check(whole: str, namespace: str, name: str, against: xmlschema.XMLSchema) -> None:
    try:
        root = ET.fromstring(whole.encode("utf-8"))
    except ET.ParseError as error:
        raise SchemaError(f"The document is not well-formed XML: {error}.") from None
    body = root.find(f".//{{{namespace}}}{name}")
    if body is None:
        raise SchemaError(f"The document is not a VeriFactu {name}.")
    error = next(iter(against.iter_errors(body)), None)
    if error is not None:
        raise SchemaError(_summary(error))


def validate(whole: str) -> None:
    """Validate a submission (a SOAP envelope); ``SchemaError`` names the first thing the AEAT would refuse."""
    _check(whole, envelope.SUM, "RegFactuSistemaFacturacion", schema())


def validate_query(whole: str) -> None:
    """Validate a query (a SOAP envelope) against the AEAT's ``ConsultaLR.xsd``."""
    _check(whole, envelope.CON, "ConsultaFactuSistemaFacturacion", query_schema())


def validate_record(registro: str, *, obligado_name: str, obligado_nif: str) -> None:
    """Validate one record as it would travel alone."""
    validate(
        envelope.submission(
            obligado_name=obligado_name, obligado_nif=obligado_nif, registros=[registro]
        )
    )
