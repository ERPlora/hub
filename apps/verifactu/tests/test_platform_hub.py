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

    assert queries.route_problem(config, Environment.PRODUCTION, PLATFORM) == ""
    # Only on ERPlora's own hub (saas#2524): the same tax ID on any other business is no exemption.
    assert queries.route_problem(config, Environment.PRODUCTION, A) == "representation_not_approved"


def test_any_other_issuer_needs_its_approved_authorisation(db, settings):
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"
    run("invoice.issuer.update", ISSUER)
    config = Config(
        route=Config.Route.ERPLORA, representation_status=Config.Representation.NONE
    )

    assert (
        queries.route_problem(config, Environment.PRODUCTION, A)
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
    # The SaaS knows ERPlora's own hub by ``PLATFORM_HUB_SLUG`` and any other by its host's slug (saas#29). ERPlora's
    # own hub presents ERPlora's own records: its issuer is ERPlora (hub#454: a business's tax ID on that scope is
    # not ERPlora's record, see the tests below).
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    if scope is PLATFORM:
        settings.PLATFORM_ISSUER_TAX_ID = ISSUER["tax_id"]
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
        {"version": 1, "representation": {"status": "approved"}},
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


# ── hub#454: the platform's pass presents each record as the business it belongs to ─────────────────────────────
#
# In phase 1 the worker runs the queue on its fixed scope (``WORKER_SCOPE_SLUG``, ERPlora's own hub by default) and,
# while the tables are shared, that pass sees the businesses' records too. Presenting them as ``erplora`` made the
# SaaS's gateway refuse them (409 ``nif_mismatch``: the platform's hub files ERPlora's own records only), so no ticket
# reached the AEAT. A business's record is presented as its business (the id erplora.com gave it, ``Config.hub_id``,
# which the SaaS takes as well as a slug); without it, nothing is presented and the record says why.

BUSINESS_ID = "0192f0a3-8c4e-7d21-9b6a-3f5e2d1c0b7a"
URL = "http://saas.internal:8001"


@pytest.fixture
def platform_pass(db, platform_slug, settings):
    """The worker's pass on ERPlora's own hub in ``pre`` (the AEAT's test environment), with a business's issuer."""
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.VERIFACTU_GATEWAY_URL = URL
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"
    ctx = ctx_for(scope=PLATFORM)
    run("invoice.issuer.update", ISSUER, ctx)
    return ctx


def linked(version: int = 1) -> None:
    """erplora.com's photo of the business, with its id (``base.services._sync_verifactu``)."""
    run("verifactu.config.sync", {"version": version, "hub_id": BUSINESS_ID}, system_context(A))


def sealed(ctx) -> Record:
    invoice = run(
        "invoice.invoice.create",
        {
            "lines": [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
            "series_code": "TICKET",
        },
        ctx,
    )
    return Record.objects.get(pk=run("verifactu.record.create", {"invoice_id": str(invoice.id)}, ctx).record.id)


def busy() -> httpx.Response:
    return httpx.Response(503, json={"error": {"code": "gateway_busy", "message": "Busy."}})


def test_the_platforms_pass_presents_a_business_record_as_its_business(platform_pass):
    linked()
    sealed(platform_pass)
    with respx.mock:
        door = respx.post(f"{URL}/internal/verifactu/submit").mock(return_value=busy())
        run("verifactu.contingency.process", None, platform_pass)

    assert door.call_count == 1
    sent = json.loads(door.calls.last.request.content)
    assert (sent["hub"], sent["nif"]) == (BUSINESS_ID, ISSUER["tax_id"])


def test_without_the_business_link_nothing_is_presented_and_the_record_says_why(platform_pass):
    record = sealed(platform_pass)
    with respx.mock(assert_all_called=False) as mock:
        door = mock.post(f"{URL}/internal/verifactu/submit").mock(return_value=busy())
        out = run("verifactu.contingency.process", None, platform_pass)

    assert door.call_count == 0
    assert out.reason == "hub_unregistered"
    record.refresh_from_db()
    assert (record.status, record.attempts, record.wait_reason) == ("pending", 0, "hub_unregistered")
    waiting = run("verifactu.record.get", {"record_id": str(record.id)}, platform_pass).waiting
    assert [reason.code for reason in waiting] == ["hub_unregistered"]


def test_once_erplora_links_the_business_its_record_stops_waiting_and_goes_out_as_late(platform_pass):
    record = sealed(platform_pass)
    run("verifactu.contingency.process", None, platform_pass)

    linked()

    waiting = run("verifactu.record.get", {"record_id": str(record.id)}, platform_pass).waiting
    assert "hub_unregistered" not in {reason.code for reason in waiting}
    with respx.mock:
        door = respx.post(f"{URL}/internal/verifactu/submit").mock(return_value=busy())
        run("verifactu.contingency.process", None, platform_pass)
    sent = json.loads(door.calls.last.request.content)
    assert sent["hub"] == BUSINESS_ID
    # It did not leave when it was sealed: it goes declared as late (Incidencia), as every record that waited.
    assert "<sum1:Incidencia>S</sum1:Incidencia>" in sent["envelope"]


def test_sending_it_by_hand_without_the_link_is_refused_with_the_reason(platform_pass):
    record = sealed(platform_pass)

    refused = code_of(
        lambda: run("verifactu.record.transmit", {"record_id": str(record.id)}, platform_pass)
    )

    assert refused == "verifactu.hub_unregistered"


@pytest.mark.parametrize("tax_id", ["B27593136", " b27593136 "], ids=["as-is", "spaced-lowercase"])
def test_erploras_own_records_are_still_presented_as_erploras_hub(platform_pass, tax_id):
    run("invoice.issuer.update", {**ISSUER, "tax_id": tax_id}, platform_pass)
    linked()
    sealed(platform_pass)
    with respx.mock:
        door = respx.post(f"{URL}/internal/verifactu/submit").mock(return_value=busy())
        run("verifactu.contingency.process", None, platform_pass)

    assert json.loads(door.calls.last.request.content)["hub"] == PLATFORM.key


def test_the_connection_test_on_the_platform_presents_the_business(platform_pass):
    linked()
    with respx.mock:
        probe = respx.post(f"{URL}/internal/verifactu/probe").mock(
            return_value=httpx.Response(200, json={"ready": True, "message": "Ready."})
        )
        run("verifactu.diagnostic.run", None, platform_pass)

    assert json.loads(probe.calls.last.request.content)["hub"] == BUSINESS_ID


def test_the_connection_test_without_the_link_asks_nothing_and_says_why(platform_pass):
    with respx.mock(assert_all_called=False) as mock:
        probe = mock.post(f"{URL}/internal/verifactu/probe").mock(
            return_value=httpx.Response(200, json={"ready": True, "message": "Ready."})
        )
        result = run("verifactu.diagnostic.run", None, platform_pass)

    assert probe.call_count == 0
    assert result.can_send is False
    assert "hub_unregistered" in {reason.code for reason in result.reasons}


def test_the_aeat_query_on_the_platform_presents_the_business(platform_pass):
    linked()
    with respx.mock:
        door = respx.post(f"{URL}/internal/verifactu/query").mock(return_value=busy())
        code_of(
            lambda: run(
                "verifactu.aeat.query",
                {"issuer_nif": ISSUER["tax_id"], "year": 2026, "month": 10},
                platform_pass,
            )
        )

    assert json.loads(door.calls.last.request.content)["hub"] == BUSINESS_ID


def test_the_aeat_query_without_the_link_asks_nothing_and_says_why(platform_pass):
    with respx.mock(assert_all_called=False) as mock:
        door = mock.post(f"{URL}/internal/verifactu/query").mock(return_value=busy())
        refused = code_of(
            lambda: run(
                "verifactu.aeat.query",
                {"issuer_nif": ISSUER["tax_id"], "year": 2026, "month": 10},
                platform_pass,
            )
        )

    assert door.call_count == 0
    assert refused == "verifactu.hub_unregistered"
