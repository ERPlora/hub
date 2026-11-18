"""Spain's trusted list (TSL) read into the list of recognised authorities the app keeps (``trust``).

The Ministry publishes it at ``TSL_URL``, the address the EU's list of trusted lists gives for Spain, in the ETSI
TS 119 612 layout. What is kept: the certificate of every service of qualified certificates (``CA/QC``) for electronic
signatures or seals (not only for websites) that has not expired, with the moment it was withdrawn if it was. The
list is read by a person who renews it (``manage.py verifactu_trusted_list``), never while serving a request.
"""

import base64
import binascii
import datetime as dt
import urllib.request
from xml.etree import ElementTree as ET

from cryptography import x509
from cryptography.hazmat.primitives import serialization

TSL_URL = "https://tsl.digital.gob.es/TSL.xml"
DOWNLOAD_TIMEOUT_SECONDS = 60

_NS = {"tsl": "http://uri.etsi.org/02231/v2#"}
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_CA_QC = "http://uri.etsi.org/TrstSvc/Svctype/CA/QC"
_WITHDRAWN = "http://uri.etsi.org/TrstSvc/TrustedList/Svcstatus/withdrawn"
_FOR_SIGNATURES_OR_SEALS = {
    "http://uri.etsi.org/TrstSvc/TrustedList/SvcInfoExt/ForeSignatures",
    "http://uri.etsi.org/TrstSvc/TrustedList/SvcInfoExt/ForeSeals",
}


class TrustedListInvalid(ValueError):
    """What was read is not Spain's trusted list."""


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as answer:
        return answer.read()


def read(xml: bytes, now: dt.datetime) -> dict:
    """The kept list's content from the TSL ``xml``; ``TrustedListInvalid`` if it is not Spain's."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise TrustedListInvalid("The file is not XML.") from None
    scheme = root.find("tsl:SchemeInformation", _NS)
    if root.tag != "{%s}TrustServiceStatusList" % _NS["tsl"] or scheme is None:
        raise TrustedListInvalid("The file is not a trusted list (ETSI TS 119 612).")
    territory = scheme.findtext("tsl:SchemeTerritory", namespaces=_NS)
    if territory != "ES":
        raise TrustedListInvalid(f"The trusted list is not Spain's but {territory!r}.")
    sequence = scheme.findtext("tsl:TSLSequenceNumber", namespaces=_NS) or ""
    if not sequence.strip().isdigit():
        raise TrustedListInvalid("The trusted list has no sequence number.")
    return {
        "source": TSL_URL,
        "sequence": int(sequence),
        "issued_at": scheme.findtext("tsl:ListIssueDateTime", namespaces=_NS),
        "next_update": scheme.findtext("tsl:NextUpdate/tsl:dateTime", namespaces=_NS),
        "authorities": _authorities(root, now),
    }


def _authorities(root: ET.Element, now: dt.datetime) -> list[dict]:
    """One entry per certificate, the most favourable listing of it (still qualified before withdrawn)."""
    kept: dict[str, dict] = {}
    for provider in root.iterfind(".//tsl:TrustServiceProvider", _NS):
        provider_name = _name(provider.find("tsl:TSPInformation/tsl:TSPName", _NS))
        for info in provider.iterfind("tsl:TSPServices/tsl:TSPService/tsl:ServiceInformation", _NS):
            for entry in _entries(info, provider_name, now):
                earlier = kept.get(entry["certificate"])
                if earlier is None or _qualified_longer(entry, earlier):
                    kept[entry["certificate"]] = entry
    return sorted(kept.values(), key=lambda entry: (entry["provider"], entry["service"], entry["certificate"]))


def _entries(info: ET.Element, provider: str, now: dt.datetime) -> list[dict]:
    if info.findtext("tsl:ServiceTypeIdentifier", namespaces=_NS) != _CA_QC:
        return []
    uses = {uri.text for uri in info.iterfind(".//tsl:AdditionalServiceInformation/tsl:URI", _NS)}
    if not uses & _FOR_SIGNATURES_OR_SEALS:
        return []
    withdrawn_at = None
    if info.findtext("tsl:ServiceStatus", namespaces=_NS) == _WITHDRAWN:
        withdrawn_at = dt.datetime.fromisoformat(info.findtext("tsl:StatusStartingTime", namespaces=_NS)).isoformat()
    service = _name(info.find("tsl:ServiceName", _NS))
    entries = []
    for value in info.iterfind("tsl:ServiceDigitalIdentity/tsl:DigitalId/tsl:X509Certificate", _NS):
        certificate = _certificate(value.text or "")
        if certificate.not_valid_after_utc > now:
            der = certificate.public_bytes(serialization.Encoding.DER)
            entries.append(
                {
                    "provider": provider,
                    "service": service,
                    "withdrawn_at": withdrawn_at,
                    "certificate": base64.b64encode(der).decode(),
                }
            )
    return entries


def _certificate(text: str) -> x509.Certificate:
    try:
        return x509.load_der_x509_certificate(base64.b64decode("".join(text.split()), validate=True))
    except ValueError, binascii.Error:
        raise TrustedListInvalid("A certificate in the trusted list cannot be read.") from None


def _qualified_longer(entry: dict, than: dict) -> bool:
    """Whether ``entry`` keeps the authority qualified longer than ``than`` (no withdrawal: still qualified)."""
    if than["withdrawn_at"] is None:
        return False
    if entry["withdrawn_at"] is None:
        return True
    return dt.datetime.fromisoformat(entry["withdrawn_at"]) > dt.datetime.fromisoformat(than["withdrawn_at"])


def _name(names: ET.Element | None) -> str:
    """The English name of a provider or service, else the first one, its spaces collapsed."""
    found = [] if names is None else names.findall("tsl:Name", _NS)
    english = [name for name in found if name.get(_XML_LANG) == "en"]
    chosen = (english or found)[:1]
    return " ".join((chosen[0].text or "").split()) if chosen else ""
