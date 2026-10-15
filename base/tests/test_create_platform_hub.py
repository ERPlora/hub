"""``manage.py create_platform_hub [--execute]``: ERPlora's own hub, brought up repeatably (plan 2026-10-15, task 4.8).

Ported from the old SaaS's ``ensure_platform_hub`` (hubs/main/tests/test_ensure_platform_hub.py): idempotent, a dry
run unless ``--execute``, it names what it found and refuses rather than guesses — one hub is one issuer is one chain,
so it never writes over another identity. Phase 1 has neither the control registry nor hub databases: the platform
hub is its reserved slug (``PLATFORM_HUB_SLUG``, which no business can take) on the one database, so "creating" it is
giving it its issuer (``PLATFORM_ISSUER_*``) and pinning VeriFactu to the deployment's environment; Invoicing and
VeriFactu are always active in phase 1.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from live.context import Scope, system_context
from live.slugs import validate_hub_slug

from apps.invoice.models import Issuer
from apps.invoice.tests.conftest import ISSUER, run
from apps.verifactu.models import Config, Environment

PLATFORM = Scope("host", "erplora")


@pytest.fixture
def deployment(db, settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.PLATFORM_ISSUER_LEGAL_NAME = "ERPLORA CLOUD SL"
    settings.PLATFORM_ISSUER_TAX_ID = "B12345674"
    settings.PLATFORM_ISSUER_ADDRESS = "Avda. de Lisboa, 17, 2º C"
    settings.PLATFORM_ISSUER_POSTAL_CODE = "28822"
    settings.PLATFORM_ISSUER_CITY = "Coslada"
    settings.PLATFORM_ISSUER_PROVINCE = "Madrid"
    settings.PLATFORM_ISSUER_COUNTRY = "ES"
    return settings


def command(*args) -> str:
    out = StringIO()
    call_command("create_platform_hub", *args, stdout=out)
    return out.getvalue()


def test_its_slug_is_reserved_so_no_business_can_take_it(deployment):
    with pytest.raises(ValueError):
        validate_hub_slug(deployment.PLATFORM_HUB_SLUG)


def test_without_execute_nothing_is_written_and_it_says_what_it_would_do(deployment):
    out = command()

    assert not Issuer.objects.exists()
    assert not Config.objects.exists()
    assert "Dry run" in out
    assert "would set the issuer ERPLORA CLOUD SL (B12345674)" in out


def test_it_sets_the_issuer_from_the_environment(deployment):
    out = command("--execute")

    issuer = Issuer.objects.get()
    assert (
        issuer.legal_name,
        issuer.tax_id,
        issuer.address,
        issuer.postal_code,
        issuer.city,
        issuer.province,
        issuer.country,
    ) == (
        "ERPLORA CLOUD SL",
        "B12345674",
        "Avda. de Lisboa, 17, 2º C",
        "28822",
        "Coslada",
        "Madrid",
        "ES",
    )
    assert "issuer set" in out
    assert "ready to issue ERPlora's invoices" in out


@pytest.mark.parametrize(
    ("where", "opened", "environment"),
    [
        ("pre", True, Environment.TESTING),
        ("prod", True, Environment.PRODUCTION),
        # Working-rules §15: closed on the server, ERPlora's own hub files in testing like any business.
        ("prod", False, Environment.TESTING),
    ],
)
def test_verifactu_files_where_the_deployment_does(
    deployment, where, opened, environment
):
    deployment.ERPLORA_ENVIRONMENT = where
    deployment.VERIFACTU_PRODUCTION_ENABLED = opened

    command("--execute")

    config = Config.objects.get()
    assert (config.environment, config.route) == (environment, Config.Route.ERPLORA)
    assert (config.production_since is not None) is (
        environment == Environment.PRODUCTION
    )


def test_running_it_twice_writes_nothing_the_second_time(deployment):
    command("--execute")
    issuer = Issuer.objects.get()
    config = Config.objects.get()

    out = command("--execute")

    assert Issuer.objects.get().updated_at == issuer.updated_at
    assert Config.objects.get().updated_at == config.updated_at
    assert "issuer found" in out


def test_another_identity_on_the_database_is_never_overwritten(deployment):
    # Phase 1 has one database: an issuer that is not ERPlora's is a business's, and its chain is its own.
    run(
        "invoice.issuer.update",
        {**ISSUER, "tax_id": "B27593136"},
        system_context(PLATFORM),
    )

    with pytest.raises(CommandError, match="B27593136"):
        command("--execute")

    assert Issuer.objects.get().tax_id == "B27593136"
    assert not Config.objects.exists()


def test_without_an_issuer_in_the_environment_it_refuses(deployment):
    deployment.PLATFORM_ISSUER_TAX_ID = ""

    with pytest.raises(CommandError, match="PLATFORM_ISSUER_TAX_ID"):
        command("--execute")

    assert not Issuer.objects.exists()


def test_it_reminds_what_real_filing_still_needs(deployment):
    deployment.ERPLORA_ENVIRONMENT = "prod"
    deployment.VERIFACTU_PRODUCTION_ENABLED = False

    out = command()

    assert "would pin VeriFactu to testing" in out
    assert "VERIFACTU_PRODUCTION_ENABLED" in out
    assert "PLATFORM_INVOICING_ENABLED" in out
    assert "FISCAL_SEAL_CURRENT" in out


def test_with_production_open_its_dry_run_pins_production(deployment):
    deployment.ERPLORA_ENVIRONMENT = "prod"
    deployment.VERIFACTU_PRODUCTION_ENABLED = True

    out = command()

    assert "would pin VeriFactu to production" in out
