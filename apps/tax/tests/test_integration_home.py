"""Taxes on the Home (PLAN-HUB round 2026-10-21; FIX-TAX-SETUP-HOOKS): base's own query brings the old module's item
«Your taxes» (module.json `setup`, taxes#19), important, pending while no active root rule of any country applies
today (TAX-F17, the query the notice of the tax screens reads), to whoever manages taxes, leading to the rules. Every
change of it records an event it is refreshed on, and a change in hub B re-runs B's Home only; with Taxes off the Home
does not ask.

base and tax run for real: the step comes from TaxConfig through base's own query, as the person.
"""

import json
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from django.apps import apps
from django.utils import timezone
from live.context import OperationContext, Scope
from live.live_registry import live_registry
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.tests.conftest import A, B
from base.schemas import SetupStatusIn
from base.services import AppRequired

STEP = "tax.rules"
CATEGORY = "product.generic"
WAIT = 1.0
QUIET = 0.3


def person(
    role: str = "hub_owner", scope: Scope = A, language: str = "en", permissions: set[str] | None = None
) -> OperationContext:
    """Whoever reads the Home: the role's permissions on ``scope`` (``permissions`` replaces them), in ``language``."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor="tester", permissions=permissions, language=language)


def step(ctx=None) -> dict | None:
    """Taxes' step of «Finish setting up your business» for the person of ``ctx`` (``None``: not told)."""
    items = get("base.setup.status")(ctx or person(), SetupStatusIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "tax"]
    assert len(found) <= 1, found
    return found[0] if found else None


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or person("hub_admin"), op.input.model_validate(data))


def today():
    return timezone.localdate()


@pytest.fixture
def generic(no_seed):
    """A hub with one tax category and no rule at all (the factory catalogue removed)."""
    return TaxCategory.objects.create(key=CATEGORY, name="Generic")


def rule(category: TaxCategory, **fields) -> TaxRule:
    """A Spanish root rule at 21 % of ``category``, in force since always unless ``fields`` say otherwise."""
    return TaxRule.objects.create(category=category, **{"country_code": "ES", "rate_pct": Decimal("21"), **fields})


@pytest.mark.django_db
def test_a_hub_without_rules_has_your_taxes_pending_and_it_leads_to_the_rules(generic):
    item = step()
    assert {name: item[name] for name in ("key", "state", "level", "required", "actionable", "route", "order", "icon")} == {
        "key": STEP,
        "state": "pending",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/tax/rules",
        "order": 20,
        "icon": "ion:receipt-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your taxes",
        "Set up the VAT rates of the country you sell in so the till can price a sale.",
    )


@pytest.mark.django_db
def test_in_spanish_it_says_the_words_of_the_notice(generic):
    # gh:hub#2356: the old checklist said a module's step in English to a Spanish reader.
    item = step(person(language="es"))
    assert (item["title"], item["description"]) == (
        "Tus impuestos",
        "Configura los tipos de IVA del país en el que vendes para que el TPV pueda calcular el precio de una venta.",
    )


@pytest.mark.django_db
def test_the_factory_spanish_rules_tick_it():
    # TAX-F16: every hub is born with the Spanish VAT rules, so a new hub is done already.
    assert step()["state"] == "done"


@pytest.mark.django_db
def test_one_root_rule_in_force_today_ticks_it_whatever_its_country_or_class(generic):
    rule(generic, country_code="PT", rate_pct=Decimal("0"), operation_class="exempt")
    assert step()["state"] == "done"


@pytest.mark.django_db
def test_a_rule_that_does_not_apply_today_does_not_tick_it(generic):
    # Ended yesterday, starting tomorrow, deactivated, or a component hanging from a root that is off: the till could
    # not price a sale with any of them.
    rule(generic, valid_to=today() - timedelta(days=1))
    rule(generic, valid_from=today() + timedelta(days=1))
    root = rule(TaxCategory.objects.create(key="product.other", name="Other"), is_active=False)
    TaxRule.objects.create(
        category=root.category, country_code="ES", rate_pct=Decimal("5.2"), parent=root, tax_type="surcharge"
    )
    assert step()["state"] == "pending"


@pytest.mark.django_db
def test_whoever_manages_taxes_is_told_and_who_only_reads_them_is_not(generic):
    # Important, never ⛔: who cannot set the rates up is not told (base's rule). The employee only reads them.
    assert step(person("hub_admin"))["state"] == "pending"
    assert step(person("hub_manager"))["state"] == "pending"
    assert step(person("hub_employee")) is None


ADMINISTRATOR = OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}))


def turn_off(app: str) -> None:
    """Turns ``app`` off in hub A, after every module on that needs it (base refuses the other way round)."""
    try:
        run("base.app.disable", {"app": app}, ADMINISTRATOR)
    except AppRequired as refusal:
        for other in refusal.required_by:
            turn_off(other)
        run("base.app.disable", {"app": app}, ADMINISTRATOR)


@pytest.mark.django_db
def test_with_taxes_off_the_home_does_not_ask_for_its_rates(generic):
    # base brings only the steps of the modules on in the scope: Taxes off (after the apps that need it), no step.
    turn_off("tax")
    assert step() is None
    assert step(person(scope=B))["state"] == "pending"


def create_one(category, existing):
    run("tax.rule.create", {"country_code": "ES", "tax_category_key": CATEGORY, "rate_pct": "21"})


def create_many(category, existing):
    run(
        "tax.rule.bulk_create",
        {"rules": [{"country_code": "PT", "tax_category_key": CATEGORY, "rate_pct": "23"}]},
    )


def end(category, existing):
    run("tax.rule.end", {"id": str(existing.id), "valid_to": (today() - timedelta(days=1)).isoformat()})


def deactivate(category, existing):
    run("tax.rule.deactivate", {"id": str(existing.id)})


def activate(category, existing):
    run("tax.rule.activate", {"id": str(existing.id)})


#: Each event of the step's ``refresh_on`` → the change that records it and the state it leaves the step in.
CHANGES = {
    "tax.rule.created": [(create_one, "done"), (create_many, "done")],
    "tax.rule.ended": [(end, "pending")],
    "tax.rule.deactivated": [(deactivate, "pending")],
    "tax.rule.activated": [(activate, "done")],
}


def start_from(change, category):
    """The one rule a change acts on, so that the change is what moves the step: one in force (since a week ago) to end
    or deactivate, a deactivated one to activate, none to create."""
    if change in (end, deactivate):
        return rule(category, valid_from=today() - timedelta(days=7))
    if change is activate:
        return rule(category, is_active=False)
    return None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,change,state",
    [(event, change, state) for event, cases in CHANGES.items() for change, state in cases],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_each_change_of_the_step_records_an_event_that_refreshes_it(generic, event, change, state):
    existing = start_from(change, generic)
    before = step()["state"]
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    change(generic, existing)
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert (before, step()["state"]) == ("done" if state == "pending" else "pending", state)
    assert recorded & set(tax_app().setup[0].refresh_on) == {event}


def tax_app():
    return apps.get_app_config("tax")


def test_the_step_is_refreshed_on_nothing_else():
    assert set(tax_app().setup[0].refresh_on) == set(CHANGES)


def test_base_re_runs_the_home_on_them():
    assert set(CHANGES) <= set(live_registry.subscribable["base.setup.status"])


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_rule_created_in_hub_b_re_runs_the_home_of_b_and_tells_a_nothing(listen):
    # A transactional test may start after another one flushed the factory catalogue.
    TaxCategory.objects.get_or_create(key=CATEGORY, defaults={"name": "Generic"})
    on_a, on_b = listen(A), listen(B)
    run(
        "tax.rule.create",
        {"country_code": "PT", "tax_category_key": CATEGORY, "rate_pct": "23"},
        person("hub_admin", B),
    )

    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
