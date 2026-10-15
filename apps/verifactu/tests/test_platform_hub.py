"""ERPlora's own hub in VeriFactu (PLAN-SAAS §4; plan 2026-10-15, task 4): it files in the AEAT environment of the
deployment (prod: production; pre: testing) whatever its configuration says, so its switch is fixed (409
``verifactu.platform_fixed``); and ERPlora's seal presents ERPlora's own records without any signed authorisation
(it represents nobody), as the old SaaS filed its invoices with its own certificate.
"""

import pytest
from live.context import Scope, system_context
from live.errors import OperationError

from apps.verifactu import queries
from apps.verifactu.models import Config, Environment

from apps.verifactu.tests.conftest import A, ISSUER, run

PLATFORM = Scope("host", "erplora")


@pytest.fixture
def platform_slug(settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key


def code_of(call) -> str:
    with pytest.raises(OperationError) as failed:
        call()
    return failed.value.code


@pytest.mark.parametrize(
    ("deployment", "expected"),
    [("prod", Environment.PRODUCTION), ("pre", Environment.TESTING)],
)
def test_the_platform_hub_files_where_its_deployment_does(
    db, platform_slug, settings, deployment, expected
):
    settings.ERPLORA_ENVIRONMENT = deployment
    config = Config(
        environment=Environment.TESTING
        if expected == Environment.PRODUCTION
        else Environment.PRODUCTION
    )

    assert queries.effective_environment(system_context(PLATFORM), config) == expected


@pytest.mark.parametrize("environment", [Environment.TESTING, Environment.PRODUCTION])
def test_any_other_hub_files_where_its_configuration_says(
    db, platform_slug, settings, environment
):
    settings.ERPLORA_ENVIRONMENT = "prod"

    assert (
        queries.effective_environment(
            system_context(A), Config(environment=environment)
        )
        == environment
    )


@pytest.mark.parametrize(
    "name", ["verifactu.config.go_live", "verifactu.config.back_to_testing"]
)
def test_the_platform_hubs_switch_is_fixed(db, platform_slug, settings, name):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True

    assert (
        code_of(lambda: run(name, {}, system_context(PLATFORM)))
        == "verifactu.platform_fixed"
    )
    assert not Config.objects.filter(environment=Environment.PRODUCTION).exists()


def test_another_hubs_switch_is_still_its_own(db, platform_slug):
    # Going back to testing from testing answers the configuration: nothing is fixed for a business.
    assert (
        run("verifactu.config.back_to_testing", {}, system_context(A)).environment
        == Environment.TESTING
    )


def test_erploras_seal_files_erploras_own_records_without_an_authorisation(
    db, settings
):
    settings.PLATFORM_ISSUER_TAX_ID = ISSUER["tax_id"]
    run("invoice.issuer.update", ISSUER)
    config = Config(
        route=Config.Route.ERPLORA, representation_status=Config.Representation.NONE
    )

    assert queries.sending_problem(config, Environment.PRODUCTION) == ""


def test_any_other_issuer_needs_its_approved_authorisation(db, settings):
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"
    run("invoice.issuer.update", ISSUER)
    config = Config(
        route=Config.Route.ERPLORA, representation_status=Config.Representation.NONE
    )

    assert (
        queries.sending_problem(config, Environment.PRODUCTION)
        == "representation_not_approved"
    )
