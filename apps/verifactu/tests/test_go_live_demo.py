"""A demo hub never goes live with VeriFactu.

The demo is a row of the registry (``base.Hub.is_demo``), which ``base.operations.is_demo_hub`` reads: here a real
row, not a stand-in, with a database of its own as every demo has (``hub_b``). On a demo's scope
``verifactu.config.go_live`` is 409 ``verifactu.go_live_forbidden`` even on a server open for production with a route
ready; on a business's (``A``) the same server lets it go live.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict

from apps.verifactu import certificates
from apps.verifactu.models import Config, Environment, Record
from apps.verifactu.queries import production_open
from apps.verifactu.tests.conftest import HUB_DB, ISSUER, A, B, ctx_for, run
from base.models import Hub

pytestmark = HUB_DB

DEMO = B


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway: going live is possible on this server."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


def route_ready(scope):
    """ERPlora's approved authorisation: the route to production is ready, on any plan."""
    run(
        "verifactu.config.sync",
        {"version": 1, "representation": {"status": "approved"}},
        system_context(scope),
    )


@pytest.fixture
def ready_route(issuer):
    route_ready(A)


@pytest.fixture
def demo(hub_b, in_business_b):
    """``demo()``: inside a live demo that turned its apps on, with its issuer and the same ready route."""
    Hub.objects.filter(pk=hub_b.pk).update(is_demo=True, expires_at=timezone.now() + dt.timedelta(hours=1))
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=DEMO))
        route_ready(DEMO)
    return in_business_b


@pytest.mark.usefixtures("opened", "ready_route")
def test_a_demo_never_goes_live_even_on_a_server_open_for_it(demo):
    assert production_open()
    with demo(), pytest.raises(Conflict) as refused:
        run("verifactu.config.go_live", ctx=ctx_for(scope=DEMO))
    assert (refused.value.status, refused.value.code) == (409, "verifactu.go_live_forbidden")
    with demo():
        assert Config.objects.get().environment == "testing"


@pytest.mark.usefixtures("opened", "ready_route", "demo")
def test_a_business_on_the_same_server_goes_live():
    run("verifactu.config.go_live", ctx=ctx_for(scope=A))
    assert Config.objects.get().environment == "production"


@pytest.mark.usefixtures("opened")
def test_a_demo_files_in_testing_even_where_the_configuration_says_production(demo):
    # Nothing of a demo ever reaches the real AEAT. No operation lets a demo go live, so its configuration is
    # written as production by hand: the demo's sale is still sealed in the test environment, never numbered in
    # production.
    with demo():
        Config.objects.update(environment=Environment.PRODUCTION)
        invoice = run(
            "invoice.invoice.create",
            {
                "lines": [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
                "series_code": "TICKET",
            },
            ctx_for(scope=DEMO),
        )

        record = Record.objects.get(invoice_id=invoice.id)
    assert record.environment == "testing"
    assert "prewww2.aeat.es" in record.qr_url
