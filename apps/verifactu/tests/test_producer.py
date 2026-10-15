"""The software producer's facts (VERIFACTU-F12): what the signed responsible declaration states, and the
``SistemaInformatico`` block every record carries."""

import json
from pathlib import Path

import pytest

from apps.verifactu import producer

#: The signed declaration, as the SaaS publishes it (saas-next/public/declaracion/v1). When both repos sit
#: side by side (the erplora-next checkout) the constants are checked against it; on its own the Hub keeps
#: the values the test pins below.
DECLARATION = (
    Path(__file__).resolve().parents[4]
    / "saas-next"
    / "public"
    / "declaracion"
    / "v1"
    / "declared-facts.json"
)


def test_the_manufacturer_is_erplora_as_declared():
    assert producer.MANUFACTURER == {
        "NombreRazon": "ERPLORA CLOUD SL",
        "NIF": "B27593136",
        "NombreSistemaInformatico": "ERPlora Hub",
        "IdSistemaInformatico": "EC",
        "TipoUsoPosibleSoloVerifactu": "S",
        "TipoUsoPosibleMultiOT": "S",
    }
    assert producer.DECLARATION_VERSION == "v1"


@pytest.mark.skipif(
    not DECLARATION.exists(), reason="saas-next is not checked out next to hub-next"
)
def test_the_constants_are_the_signed_declarations():
    declared = json.loads(DECLARATION.read_text())
    assert declared["status"] == "signed"
    assert declared["facts"] == producer.MANUFACTURER


def test_the_system_block_merges_the_manufacturer_with_this_installation():
    system = producer.system_info(version="abc123", installation="peluqueria-ana")
    assert system.name == "ERPLORA CLOUD SL"
    assert system.nif == "B27593136"
    assert system.system_name == "ERPlora Hub"
    assert system.system_id == "EC"
    assert system.version == "abc123"
    assert system.installation == "peluqueria-ana"
    assert (system.only_verifactu, system.multi_ot, system.multiple_ot) == (
        "S",
        "S",
        "S",
    )


def test_erplora_always_serves_several_taxpayers():
    # IndicadorMultiplesOT: ERPlora is one platform for many businesses, a multi-taxpayer system by definition,
    # so it is «S» on every record and owes nothing to the account's photo (decision of 2026-10-15, T2b).
    assert producer.MULTIPLE_OT == "S"
    assert producer.system_info(version="abc", installation="a").multiple_ot == "S"


def test_a_version_and_an_installation_fit_the_schema():
    system = producer.system_info(version="x" * 80, installation="h" * 150)
    assert len(system.version) == 50
    assert len(system.installation) == 100


def test_the_running_version_is_the_images_commit_or_dev(settings):
    settings.APP_VERSION = "9eede33"
    assert producer.running_version() == "9eede33"
    settings.APP_VERSION = ""
    assert producer.running_version() == "dev"


def test_the_declaration_url_is_the_saas_public_page(settings):
    settings.SAAS_URL = "https://erplora.com"
    assert (
        producer.declaration_url()
        == "https://erplora.com/legal/declaracion-responsable/v1/"
    )
