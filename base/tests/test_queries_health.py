"""``base.health.list``: the Home's health row of the apps on in the business, for who runs it (``base.home_health``).

The stand-in modules here name a query registered for the test; Printing's own, for real, is
``apps/printing/tests/test_integration_home_health.py``.
"""

import pytest
from live.context import OperationContext
from live.operations import get

from base.models import Hub
from base.schemas.health import HealthListIn
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, A, B, in_business_a
from base.tests.test_queries_home import declare, module

__all__ = ["declare", "in_business_a"]
pytestmark = HUB_DB
HOME = "base.view_home"
ADMIN = "base.administer_hub"
HEALTH = {
    "operation": "stock.thing.health",
    "permission": "stock.view",
    "route": "/stock/setup",
    "action": "Set up the stock",
    "titles": {"ok": "Ready", "no_signal": "Quiet", "not_configured": "Not set up", "unknown": "Can't tell"},
}


@pytest.fixture
def modules(monkeypatch, settings):
    """The modules base sees, all of them on in every scope unless ``on`` says otherwise."""
    settings.SHOW_UNLISTED_MODULES = False

    def use(*configs, on=None):
        labels = {config.label for config in configs} if on is None else set(on)
        monkeypatch.setattr("base.home.module_configs", lambda: list(configs))
        monkeypatch.setattr("base.queries.health.active_apps", lambda scope: frozenset(labels | {"base"}))

    return use


@pytest.fixture
def stock(declare, modules):
    declare("stock.thing.health", {"state": "no_signal"})
    modules(module("stock", health=HEALTH, permissions=["stock.view"]), module("sale"))


def ctx(*permissions, scope=A):
    return OperationContext(scope=scope, actor="ana", permissions=frozenset({HOME, *permissions}), language="en")


def health(context) -> list[dict]:
    return get("base.health.list")(context, HealthListIn()).model_dump(mode="json")["items"]


def test_who_runs_the_business_is_told_the_state_of_each_app_on_that_declares_it(stock):
    assert health(ctx(ADMIN, "stock.view")) == [
        {
            "key": "stock",
            "app": "stock",
            "state": "no_signal",
            "title": "Quiet",
            "action": "Set up the stock",
            "route": "/stock/setup",
        }
    ]


def test_whoever_does_not_run_the_business_or_may_not_see_the_app_is_told_nothing(stock):
    assert health(ctx("stock.view")) == []
    assert health(ctx(ADMIN)) == []


def test_an_app_off_in_the_business_says_nothing_though_it_declares_its_health(declare, modules):
    declare("stock.thing.health", lambda ctx, data: pytest.fail("an app off is never asked"))
    modules(module("stock", health=HEALTH, permissions=["stock.view"]), on=[])

    assert health(ctx(ADMIN, "stock.view")) == []


def test_an_app_out_of_the_store_says_nothing_on_a_customers_business(declare, modules):
    declare("stock.thing.health", {"state": "ok"})
    modules(module("stock", health=HEALTH, permissions=["stock.view"], listed=False))

    assert health(ctx(ADMIN, "stock.view")) == []


def test_each_business_is_told_of_its_own_apps_on(declare, modules, monkeypatch, hub_b):
    declare("stock.thing.health", lambda ctx, data: {"state": "ok" if ctx.scope == A else "not_configured"})
    modules(module("stock", health=HEALTH, permissions=["stock.view"]))
    monkeypatch.setattr(
        "base.queries.health.active_apps", lambda scope: frozenset({"base", "stock"} if scope.key == A.key else {"base"})
    )

    assert [item["state"] for item in health(ctx(ADMIN, "stock.view"))] == ["ok"]
    with use_hub(Hub.objects.get(slug=B.key)):
        assert health(ctx(ADMIN, "stock.view", scope=B)) == []
