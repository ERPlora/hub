"""ERPlora's own hub in VeriFactu (PLAN-SAAS §4; plan 2026-10-15, task 4): it files in the AEAT environment of the
deployment (prod: production; pre: testing) whatever its configuration says, so its switch is fixed (409
``verifactu.platform_fixed``); and ERPlora's seal presents ERPlora's own records without any signed authorisation
(it represents nobody), as the old SaaS filed its invoices with its own certificate. Production, though, only once
ERPlora opens it on the server (``VERIFACTU_PRODUCTION_ENABLED``, working-rules §15): its own invoices skip no lock.
"""

import json

import httpx
import pytest
import respx
from live.context import Scope, system_context
from live.errors import OperationError

from apps.verifactu import queries
from apps.verifactu.models import Config, Environment, Record

from apps.verifactu.tests.conftest import A, ISSUER, ctx_for, run

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
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    config = Config(
        environment=Environment.TESTING
        if expected == Environment.PRODUCTION
        else Environment.PRODUCTION
    )

    assert queries.effective_environment(system_context(PLATFORM), config) == expected


def test_the_platform_hub_skips_no_production_lock(db, platform_slug, settings):
    # Working-rules §15: real filing opens under Ioan's supervision, for ERPlora's own invoices too.
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = False

    assert (
        queries.effective_environment(
            system_context(PLATFORM), Config(environment=Environment.TESTING)
        )
        == Environment.TESTING
    )


def test_once_live_the_platform_hub_keeps_its_chain_in_production_while_closed(
    db, platform_slug, settings
):
    # Closing the server after it went live never moves ERPlora's real invoices to the test chain: they are
    # sealed in production and wait (``production_closed``) until it opens again.
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = False

    assert (
        queries.effective_environment(
            system_context(PLATFORM), Config(environment=Environment.PRODUCTION)
        )
        == Environment.PRODUCTION
    )


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
    db, platform_slug, settings
):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.PLATFORM_ISSUER_TAX_ID = ISSUER["tax_id"]
    run("invoice.issuer.update", ISSUER, ctx_for(scope=PLATFORM))
    config = Config(
        route=Config.Route.ERPLORA, representation_status=Config.Representation.NONE
    )

    assert queries.sending_problem(config, Environment.PRODUCTION, PLATFORM) == ""
    # Only on ERPlora's own hub (saas#2524): the same tax ID on any other business is no exemption.
    assert queries.sending_problem(config, Environment.PRODUCTION, A) == "representation_not_approved"


def test_any_other_issuer_needs_its_approved_authorisation(db, settings):
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"
    run("invoice.issuer.update", ISSUER)
    config = Config(
        route=Config.Route.ERPLORA, representation_status=Config.Representation.NONE
    )

    assert (
        queries.sending_problem(config, Environment.PRODUCTION, A)
        == "representation_not_approved"
    )


@pytest.mark.parametrize(
    ("deployment", "opened", "expected"),
    [
        ("prod", True, Environment.PRODUCTION),
        ("prod", False, Environment.TESTING),
        ("pre", True, Environment.TESTING),
    ],
)
def test_the_platform_hub_takes_its_deployments_environment(
    db, platform_slug, settings, deployment, opened, expected
):
    settings.ERPLORA_ENVIRONMENT = deployment
    settings.VERIFACTU_PRODUCTION_ENABLED = opened

    answer = run("verifactu.config.follow_deployment", {}, system_context(PLATFORM))

    config = Config.objects.get()
    assert (answer.environment, config.environment) == (expected, expected)
    assert (config.production_since is not None) is (expected == Environment.PRODUCTION)


def test_closing_the_server_after_going_live_leaves_it_in_production(
    db, platform_slug, settings
):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    run("verifactu.config.follow_deployment", {}, system_context(PLATFORM))
    settings.VERIFACTU_PRODUCTION_ENABLED = False

    answer = run("verifactu.config.follow_deployment", {}, system_context(PLATFORM))

    assert (answer.environment, Config.objects.get().environment) == (
        Environment.PRODUCTION,
        Environment.PRODUCTION,
    )


def test_taking_it_again_changes_nothing(db, platform_slug, settings):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    run("verifactu.config.follow_deployment", {}, system_context(PLATFORM))
    first = Config.objects.get()

    run("verifactu.config.follow_deployment", {}, system_context(PLATFORM))

    again = Config.objects.get()
    assert (again.updated_at, again.production_since) == (first.updated_at, first.production_since)


def test_no_other_business_follows_the_deployment(db, platform_slug):
    assert (
        code_of(lambda: run("verifactu.config.follow_deployment", {}, system_context(A)))
        == "verifactu.platform_only"
    )
    assert not Config.objects.exists()


@pytest.mark.parametrize("scope", [PLATFORM, A], ids=["platform", "business"])
def test_the_gateway_is_told_the_hub_by_its_slug(db, platform_slug, settings, scope):
    # The SaaS knows ERPlora's own hub by ``PLATFORM_HUB_SLUG`` and any other by its host's slug (saas#29).
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    ctx = ctx_for(scope=scope)
    run("invoice.issuer.update", ISSUER, ctx)
    invoice = run(
        "invoice.invoice.create",
        {
            "lines": [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
            "series_code": "TICKET",
        },
        ctx,
    )
    run("verifactu.record.create", {"invoice_id": str(invoice.id)}, ctx)
    with respx.mock:
        door = respx.post("http://saas.internal:8001/internal/verifactu/submit").mock(
            return_value=httpx.Response(
                503, json={"error": {"code": "gateway_busy", "message": "Busy."}}
            )
        )
        run("verifactu.contingency.process", None, ctx)

    assert door.call_count == 1
    expected = settings.PLATFORM_HUB_SLUG if scope is PLATFORM else "a"
    assert json.loads(door.calls.last.request.content)["hub"] == expected


def test_a_business_typing_erploras_tax_id_still_needs_its_approved_authorisation(
    db, platform_slug, settings
):
    # saas#2524, the Hub's side: ERPlora's tax ID typed as an ordinary business's issuer is no exemption. Only
    # ERPlora's own hub files ERPlora's records without an authorisation: anywhere else, once the authorisation is
    # revoked, a new sale in production is refused before anything is numbered (the gateway would refuse it too, and
    # the sale would be charged with no way to the AEAT, HUB-F313).
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    run("invoice.issuer.update", ISSUER)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    run("verifactu.config.go_live")
    run(
        "verifactu.config.sync",
        {"version": 2, "representation": {"status": "revoked"}},
        system_context(A),
    )
    run("invoice.issuer.update", {**ISSUER, "tax_id": settings.PLATFORM_ISSUER_TAX_ID})

    refused = code_of(
        lambda: run(
            "invoice.invoice.create",
            {
                "lines": [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
                "series_code": "TICKET",
            },
        )
    )

    assert refused == "verifactu.representation_not_approved"
    assert not Record.objects.exists()
