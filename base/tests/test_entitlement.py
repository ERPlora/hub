"""Which apps a business has the right to use (BASE-G12, PLAN §20.4–§20.5): the SaaS's photo decides, the Hub applies.

A module with ``premium = False`` always has it; one with ``premium = True`` needs its id in ``modules[]`` of the last
photo (``Hub.state``), straight or through the ``requires`` of one that is there, and a right whose ``valid_until``
passed is no right. A slug the Hub has no module for is ignored and logged. A demo's hub (no photo, no billing) has
every app. What a business has no right to is blocked everywhere: its operations answer 402
``app_entitlement_blocked`` (``LIVE["operation_database"]``) and the relay and the Home leave it out
(``base.relay.active_apps``).
"""

import datetime as dt
import logging
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.context import OperationContext, Scope
from live.operations import Operation
from pydantic import BaseModel, ConfigDict

from base import entitlement
from base.entitlement import EntitlementBlocked
from base.models import Hub
from base.relay import active_apps

A = Scope("host", "a")
B = Scope("host", "b")
NOW = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.UTC)


def module(label, *, premium=False, requires=(), name=None):
    return SimpleNamespace(label=label, premium=premium, requires=list(requires), verbose_name=name or label.capitalize())


TAX = module("tax")
STOCK = module("stock", premium=True, requires=["tax"])
INVOICE = module("invoice", premium=True, requires=["stock"])
SALE = module("sale", requires=["tax"])
CONFIGS = [TAX, STOCK, INVOICE, SALE]


def keep(slug, state):
    """The photo the SaaS last pushed for ``slug`` (``a`` and ``b`` are the suite's local hubs)."""
    Hub.objects.update_or_create(slug=slug, defaults={"status": "ready", "state": state, "state_version": 1})


def photo(*rights):
    return {"modules": [right if isinstance(right, dict) else {"id": right, "source": "purchase"} for right in rights]}


@pytest.fixture
def modules(monkeypatch):
    def use(*configs):
        monkeypatch.setattr("base.entitlement.module_configs", lambda: list(configs))

    use(*CONFIGS)
    return use


# --- The rule (pure: the photo and the modules in, the source of each right out) ------------------------------


def test_a_free_module_always_has_the_right_and_a_paid_one_needs_the_photo():
    assert entitlement.entitlements(None, now=NOW, configs=CONFIGS) == {
        "tax": "free",
        "stock": "missing",
        "invoice": "missing",
        "sale": "free",
    }
    assert entitlement.blocked(None, now=NOW, configs=CONFIGS) == frozenset({"stock", "invoice"})


def test_a_right_in_the_photo_says_where_it_comes_from():
    rights = entitlement.entitlements(
        photo({"id": "stock", "source": "plan"}, {"id": "invoice", "source": "purchase"}), now=NOW, configs=CONFIGS
    )
    assert (rights["stock"], rights["invoice"]) == ("plan", "purchase")
    assert entitlement.blocked(photo("stock", "invoice"), now=NOW, configs=CONFIGS) == frozenset()


def test_the_right_on_an_app_gives_the_right_on_what_it_requires():
    """PLAN §20.5: the SaaS knows no graph; a right on invoice is one on stock (and tax) too."""
    rights = entitlement.entitlements(photo("invoice"), now=NOW, configs=CONFIGS)
    assert rights == {"tax": "free", "stock": "required", "invoice": "purchase", "sale": "free"}
    assert entitlement.blocked(photo("invoice"), now=NOW, configs=CONFIGS) == frozenset()


def test_a_right_that_ended_is_no_right():
    ended = {"id": "stock", "source": "purchase", "valid_until": "2026-10-24T11:59:59+00:00"}
    running = {"id": "stock", "source": "purchase", "valid_until": "2026-10-24T12:00:01+00:00"}
    assert entitlement.blocked(photo(ended), now=NOW, configs=CONFIGS) == frozenset({"stock", "invoice"})
    assert entitlement.blocked(photo(running), now=NOW, configs=CONFIGS) == frozenset({"invoice"})


def test_a_slug_the_hub_has_no_module_for_is_ignored_and_logged(caplog):
    """PLAN §20.4.5: a typo in the SaaS's admin reads as «the hub never gets the right», and the log says why."""
    with caplog.at_level(logging.WARNING, logger="base.entitlement"):
        assert entitlement.blocked(photo("stok"), now=NOW, configs=CONFIGS) == frozenset({"stock", "invoice"})
    assert "stok" in caplog.text


@pytest.mark.parametrize(
    "state",
    [None, {}, {"modules": None}, {"modules": "stock"}, {"modules": [None, 3, {"source": "plan"}]}],
)
def test_a_photo_out_of_shape_gives_no_right(state):
    assert entitlement.blocked(state, now=NOW, configs=CONFIGS) == frozenset({"stock", "invoice"})


def test_a_right_with_an_unreadable_end_is_no_right(caplog):
    with caplog.at_level(logging.WARNING, logger="base.entitlement"):
        blocked = entitlement.blocked(photo({"id": "stock", "valid_until": "soon"}), now=NOW, configs=CONFIGS)
    assert blocked == frozenset({"stock", "invoice"})
    assert "soon" in caplog.text


# --- A scope's blocked apps (the registry's row of its host) -------------------------------------------------


@pytest.mark.django_db
def test_without_a_paid_module_nothing_is_read(modules):
    """Today no module is premium: blocking costs no query on any operation."""
    modules(TAX, SALE)
    with CaptureQueriesContext(connection) as queries:
        assert entitlement.blocked_apps(A) == frozenset()
    assert len(queries) == 0


@pytest.mark.django_db
def test_each_business_has_its_own_rights(modules):
    keep("a", photo("invoice"))
    keep("b", photo())

    assert entitlement.blocked_apps(A) == frozenset()
    assert entitlement.blocked_apps(B) == frozenset({"stock", "invoice"})


@pytest.mark.django_db
def test_a_demo_has_every_app(modules):
    """A demo has no photo and nothing to bill: it shows the paid apps too, so they can be tried."""
    Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True)
    assert entitlement.blocked_apps(Scope("host", "demo-0000beef")) == frozenset()


@pytest.mark.django_db
def test_a_scope_that_is_no_business_blocks_nothing(modules):
    assert entitlement.blocked_apps(Scope("platform", "registry")) == frozenset()


@pytest.mark.django_db
def test_a_host_without_a_row_has_no_paid_app(modules):
    assert entitlement.blocked_apps(Scope("host", "nobody")) == frozenset({"stock", "invoice"})


@pytest.mark.django_db
def test_the_relay_and_the_home_leave_out_what_is_blocked(modules, monkeypatch):
    """``active_apps``: what the relay delivers to and the Home asks; phase 1 has every installed app on but these."""
    monkeypatch.setattr("base.relay.all_live_app_configs", lambda: [*CONFIGS, SimpleNamespace(label="base")])
    keep("a", photo("stock"))

    assert active_apps(A) == frozenset({"base", "tax", "stock", "sale"})


# --- The gate: an operation of a blocked app answers 402 -----------------------------------------------------


class AnyIn(BaseModel):
    model_config = ConfigDict(extra="allow")


class AnyOut(BaseModel):
    model_config = ConfigDict(extra="allow")


def operation(name):
    return Operation(
        name=name,
        kind="query",
        permission=None,
        input=AnyIn,
        output=AnyOut,
        expose_api=False,
        ai=None,
        fn=lambda ctx, data: {"ran": True},
    )


def ctx(scope=A):
    return OperationContext(scope=scope, actor=None, permissions=frozenset({"*"}), language="es")


@pytest.mark.django_db
def test_an_operation_of_a_blocked_app_answers_402(modules):
    keep("a", photo())

    with pytest.raises(EntitlementBlocked) as refused:
        operation("stock.item.list")(ctx(), AnyIn())

    assert (refused.value.status, refused.value.code) == (402, "app_entitlement_blocked")
    assert "Stock" in refused.value.message and "erplora.com" in refused.value.message


@pytest.mark.django_db
def test_the_same_operation_runs_where_the_business_has_the_right(modules):
    keep("a", photo("stock"))
    keep("b", photo())

    assert operation("stock.item.list")(ctx(A), AnyIn()).model_dump() == {"ran": True}
    with pytest.raises(EntitlementBlocked):
        operation("stock.item.list")(ctx(B), AnyIn())


@pytest.mark.django_db
def test_a_free_app_and_the_platform_are_never_blocked(modules):
    keep("a", photo())
    assert operation("tax.rate.list")(ctx(), AnyIn()).model_dump() == {"ran": True}
    assert operation("base.setup.status")(ctx(), AnyIn()).model_dump() == {"ran": True}


def test_the_gate_is_the_operations_database_hook(settings):
    assert settings.LIVE["operation_database"] == "base.entitlement.operation_database"


@pytest.mark.django_db
def test_the_end_of_a_right_is_read_now(modules, monkeypatch):
    """Nobody pushes a photo when a cancelled module's period ends: the gate reads the clock."""
    ends = (timezone.now() + dt.timedelta(minutes=1)).isoformat()
    keep("a", photo({"id": "stock", "valid_until": ends}))
    assert entitlement.blocked_apps(A) == frozenset({"invoice"})
    later = timezone.now() + dt.timedelta(minutes=2)
    monkeypatch.setattr(entitlement.timezone, "now", lambda: later)
    assert entitlement.blocked_apps(A) == frozenset({"stock", "invoice"})
