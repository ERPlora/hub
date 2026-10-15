"""The software producer's facts (VERIFACTU-F12): the ``SistemaInformatico`` block of every record.

The manufacturer's identity and the product's capabilities are constants **in code** on purpose: they are what
ERPlora's signed responsible declaration states (art. 13 RRSIF; ``saas-next/public/declaracion/v1``), they
change only with a new declaration (review and git history, never a form), and a typo would be AEAT error 1100
on every record of every business. Three facts are not ERPlora's to state once for all:

- ``Version``: the running image's commit (``APP_VERSION``), ``dev`` locally;
- ``NumeroInstalacion``: this business's installation (its scope; in phase 2 the hub's id);
- ``IndicadorMultiplesOT``: the AEAT computes it **per user of the SaaS** (does the account run more than one
  facturación?), so only the account knows it and sends it (``verifactu.config.sync``). Without it there is
  no ``SistemaInformatico``: the Hub never invents a legal declaration.
"""

from dataclasses import dataclass

from django.conf import settings

#: What the signed declaration v1 states, keyed by the literal AEAT element names.
MANUFACTURER = {
    "NombreRazon": "ERPLORA CLOUD SL",
    "NIF": "B27593136",
    "NombreSistemaInformatico": "ERPlora Hub",
    "IdSistemaInformatico": "EC",
    "TipoUsoPosibleSoloVerifactu": "S",
    "TipoUsoPosibleMultiOT": "S",
}
DECLARATION_VERSION = "v1"
DECLARATION_PATH = f"/legal/declaracion-responsable/{DECLARATION_VERSION}/"
#: TextMax50Type and TextMax100Type of the schema.
VERSION_MAX_LENGTH = 50
INSTALLATION_MAX_LENGTH = 100
YES_NO = ("S", "N")


@dataclass(frozen=True)
class SystemInfo:
    """``SistemaInformatico``, in the order of its ``xs:sequence``."""

    name: str
    nif: str
    system_name: str
    system_id: str
    version: str
    installation: str
    only_verifactu: str
    multi_ot: str
    multiple_ot: str


def running_version() -> str:
    """The version this deploy declares: the image's commit, or ``dev`` without one (local)."""
    return (getattr(settings, "APP_VERSION", "") or "dev")[:VERSION_MAX_LENGTH]


def system_info(
    *, version: str, installation: str, multiple_taxpayers: str
) -> SystemInfo | None:
    """The block of this installation, or ``None`` while the account has not said ``IndicadorMultiplesOT``."""
    if multiple_taxpayers not in YES_NO:
        return None
    return SystemInfo(
        name=MANUFACTURER["NombreRazon"],
        nif=MANUFACTURER["NIF"],
        system_name=MANUFACTURER["NombreSistemaInformatico"],
        system_id=MANUFACTURER["IdSistemaInformatico"],
        version=version[:VERSION_MAX_LENGTH],
        installation=installation[:INSTALLATION_MAX_LENGTH],
        only_verifactu=MANUFACTURER["TipoUsoPosibleSoloVerifactu"],
        multi_ot=MANUFACTURER["TipoUsoPosibleMultiOT"],
        multiple_ot=multiple_taxpayers,
    )


def declaration_url() -> str:
    """The signed declaration's public page on erplora.com."""
    return f"{settings.SAAS_URL.rstrip('/')}{DECLARATION_PATH}"
