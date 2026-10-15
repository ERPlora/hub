"""The software producer's facts (VERIFACTU-F12): what the signed responsible declaration states, and the
``SistemaInformatico`` block every record carries."""

import json
import os
from pathlib import Path

import pytest

from apps.verifactu import producer

#: The SaaS checkout next to the Hub's, where its signed declaration is published
#: (public/declaracion/<version>/declared-facts.json): ``saas/`` in the erplora-next tree and in CI, which
#: fetches it; ``saas-next/`` before the folders were renamed.
SAAS_CHECKOUTS = ("saas", "saas-next")
#: The folder both repos sit in: apps/verifactu/tests/ → the Hub's checkout → its parent.
SIDE_BY_SIDE = Path(__file__).resolve().parents[4]


def find_declaration(root: Path, version: str) -> Path | None:
    """The ``version`` of the declaration in the first SaaS checkout under ``root``."""
    for checkout in SAAS_CHECKOUTS:
        path = root / checkout / "public" / "declaracion" / version / "declared-facts.json"
        if path.exists():
            return path
    return None


def declaration_or_skip(root: Path, version: str) -> Path:
    """The declaration to check against; without one, CI fails (the check must run there) and a lone
    local checkout of the Hub skips it, saying why."""
    path = find_declaration(root, version)
    if path is None:
        reason = (
            f"the SaaS's declaration {version} is not checked out next to the Hub "
            f"({' or '.join(str(root / c) for c in SAAS_CHECKOUTS)})"
        )
        if os.environ.get("CI"):
            pytest.fail(reason)
        pytest.skip(reason)
    return path


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


def test_the_constants_are_the_signed_declarations():
    declaration = declaration_or_skip(SIDE_BY_SIDE, producer.DECLARATION_VERSION)
    declared = json.loads(declaration.read_text())
    assert declared["status"] == "signed"
    assert declared["facts"] == producer.MANUFACTURER


def publish(root, checkout, version="v1"):
    folder = root / checkout / "public" / "declaracion" / version
    folder.mkdir(parents=True)
    (folder / "declared-facts.json").write_text("{}")
    return folder / "declared-facts.json"


def test_the_declaration_is_found_in_the_saas_checkout_first(tmp_path):
    saas = publish(tmp_path, "saas")
    publish(tmp_path, "saas-next")
    assert find_declaration(tmp_path, "v1") == saas


def test_the_declaration_falls_back_to_the_old_saas_next_folder(tmp_path):
    old = publish(tmp_path, "saas-next")
    assert find_declaration(tmp_path, "v1") == old


def test_the_declaration_is_the_hubs_declared_version(tmp_path):
    publish(tmp_path, "saas", version="v2")
    assert find_declaration(tmp_path, "v1") is None


def test_a_missing_declaration_fails_in_ci(tmp_path, monkeypatch):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="not checked out next to the Hub"):
        declaration_or_skip(tmp_path, "v1")


def test_a_missing_declaration_is_skipped_locally_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(pytest.skip.Exception, match="not checked out next to the Hub"):
        declaration_or_skip(tmp_path, "v1")


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
