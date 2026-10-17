"""A demo hub never goes live with VeriFactu (PLAN-SAAS §3.5; plan 2026-10-17, §1.6 point 6).

The demo is a row of the registry (``base.Hub.is_demo``), which ``base.operations.is_demo_hub`` reads: here a real
row, not a stand-in. On a demo's scope ``verifactu.config.go_live`` is 409 ``verifactu.go_live_forbidden`` even on a
server open for production with a route ready; on a business's (``a``) the same server lets it go live.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.context import Scope, system_context
from live.errors import Conflict

from apps.verifactu import certificates
from apps.verifactu.models import Config
from apps.verifactu.queries import production_open
from apps.verifactu.tests.conftest import A, ctx_for, run
from base.models import Hub

pytestmark = pytest.mark.django_db

DEMO = Scope("host", "demo-0000beef")


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway: going live is possible on this server."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


@pytest.fixture
def ready_route(issuer):
    """ERPlora's approved authorisation with the live option paid: the route to production is ready."""
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )


@pytest.fixture
def demo():
    return Hub.objects.create(
        slug=DEMO.key, is_demo=True, status="ready", expires_at=timezone.now() + dt.timedelta(hours=1)
    )


@pytest.mark.usefixtures("opened", "ready_route", "demo")
def test_a_demo_never_goes_live_even_on_a_server_open_for_it():
    assert production_open()
    with pytest.raises(Conflict) as refused:
        run("verifactu.config.go_live", ctx=ctx_for(scope=DEMO))
    assert (refused.value.status, refused.value.code) == (409, "verifactu.go_live_forbidden")
    assert Config.objects.get().environment == "testing"


@pytest.mark.usefixtures("opened", "ready_route", "demo")
def test_a_business_on_the_same_server_goes_live():
    run("verifactu.config.go_live", ctx=ctx_for(scope=A))
    assert Config.objects.get().environment == "production"
