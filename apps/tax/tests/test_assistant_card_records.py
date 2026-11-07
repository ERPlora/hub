"""FIX-HUB-TAX-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#678): the card of a write of Taxes says which rule it acts on
by its name, read as whoever asks, never by its id, and leaves it out when that person may not read it or it is not
there. A rule goes by its category, its country (and region), and its rate — a component, with its label after its
category —, what tells one rule from another on the Rules screen; and a country by its name, never its ISO code. The
datum that names a rule by its id is titled with the list's word for one («Regla»); the root rule a component hangs
from, by its field's name («Regla raíz»), never «Registro».
"""

import dataclasses
import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.operations import INTERNAL, get, registry

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.tests.conftest import A, ctx_for
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

FRONTEND = Path(apps.get_app_config("tax").path) / "frontend/locale"

#: Each write of Taxes and the datum of it that names a rule by its id.
ON_A_RULE = [
    ("tax.rule.activate", "id"),
    ("tax.rule.deactivate", "id"),
    ("tax.rule.end", "id"),
]
#: Each one that names the root rule a component hangs from.
ON_A_ROOT = [("tax.rule.create", "parent_id")]
#: Each one that names a country by its code, and where.
ON_A_COUNTRY = [
    ("tax.rule.activate", "country_code"),
    ("tax.rule.deactivate", "country_code"),
    ("tax.rule.end", "country_code"),
    ("tax.rule.create", "country_code"),
]

NBSP = "\xa0"


def screens(language: str) -> dict:
    return json.loads((FRONTEND / f"{language}.json").read_text())["tax"]


def words(language: str) -> dict[str, str]:
    """What the Rules screen calls a rule, in ``language``: as its list calls one; the root rule as its form's field
    («Root rule (component of)»), without the hint in brackets."""
    said = screens(language)["rules"]
    return {
        "rule": said["entity"]["one"].capitalize(),
        "root": said["form"]["parent"].split(" (")[0],
    }


def make_category(name: str = "Cervezas artesanas", key: str = "drink.craft_beer") -> TaxCategory:
    """A category of the business's own with every datum that could name it filled: its key, its name and its
    description."""
    return TaxCategory.objects.create(key=key, name=name, description=f"{name} de la casa")


def make_rule(
    category: TaxCategory,
    rate: str = "10",
    country: str = "ES",
    region: str = "",
    **fields,
) -> TaxRule:
    """A rule with every datum that could name it filled: its regime, its first and last day."""
    return TaxRule.objects.create(
        category=category,
        country_code=country,
        region_code=region,
        rate_pct=Decimal(rate),
        regime_key="01",
        valid_from="2026-01-01",
        valid_to="2036-12-31",
        **fields,
    )


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A rule by its name ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_RULE + ON_A_ROOT)
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Cervezas artesanas · Spain · 10%"),
        ("es", f"Cervezas artesanas · España · 10{NBSP}%"),
    ],
)
def test_a_write_says_the_rule_it_names_by_its_category_country_and_rate(write, datum, language, expected):
    """The case the issue names, «tax.rule.activate:id»: «Rule: Cervezas artesanas · Spain · 10%», never its id, its
    key or its regime; the country by its name and the rate as the person's language writes it."""
    rule = make_rule(make_category())
    assert shown(write, {datum: str(rule.id)}, language)[datum] == expected


@pytest.mark.django_db
def test_a_rule_of_a_region_says_its_region_and_a_component_its_label():
    """A rule of the Canary Islands says its region beside its country; an equivalence surcharge says its label after
    its category, as the Rules screen's card does («↳ Cervezas artesanas · Recargo de equivalencia»)."""
    category = make_category()
    canary = make_rule(category, rate="7", region="ES-CN", tax_type="igic")
    root = make_rule(category, rate="21")
    surcharge = make_rule(category, rate="5.2", parent=root, component_label="Recargo de equivalencia")
    assert shown("tax.rule.deactivate", {"id": str(canary.id)}, "es")["id"] == (
        f"Cervezas artesanas · España (ES-CN) · 7{NBSP}%"
    )
    assert shown("tax.rule.end", {"id": str(surcharge.id)}, "es")["id"] == (
        f"Cervezas artesanas · Recargo de equivalencia · España · 5,2{NBSP}%"
    )


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own rule, never another one of the business (the first, the last)."""
    beer, wine = make_category(), make_category("Vinos de la tierra", "drink.local_wine")
    rules = [make_rule(beer, rate="10"), make_rule(wine, rate="21", country="PT")]
    expected = ["Cervezas artesanas · Spain · 10%", "Vinos de la tierra · Portugal · 21%"]
    for listed, names in ((rules, expected), (list(reversed(rules)), list(reversed(expected)))):
        for write, datum in ON_A_RULE + ON_A_ROOT:
            said = [shown(write, {datum: str(rule.id)})[datum] for rule in listed]
            assert said == names, f"{write}:{datum}"


@pytest.mark.django_db
def test_a_deactivated_rule_is_still_named_to_bring_it_back():
    """Reactivating names a rule nobody applies any more: it is still there, so the card says it."""
    rule = make_rule(make_category(), is_active=False)
    assert shown("tax.rule.activate", {"id": str(rule.id)})["id"] == "Cervezas artesanas · Spain · 10%"


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(("write", "datum"), ON_A_RULE + ON_A_ROOT)
def test_the_rule_a_write_names_is_titled_with_the_screens_word_in_each_language(write, datum, language):
    """The datum that names a rule goes under the screen's word for it, never «Record» nor «Id»: «Regla» for the rule
    a write acts on, «Regla raíz» for the one a new component hangs from."""
    rule = make_rule(make_category())
    field = fields_of(write, {datum: str(rule.id)}, language)[datum]
    assert field["label"] == words(language)["rule" if datum == "id" else "root"]


@pytest.mark.django_db
def test_a_change_keeps_saying_the_rule_beside_what_it_changes():
    """Ending a rule says the rule as it is now, before the write runs, beside the last day it will apply."""
    rule = make_rule(make_category())
    assert shown("tax.rule.end", {"id": str(rule.id), "valid_to": "2026-12-31"}, "es") == {
        "id": f"Cervezas artesanas · España · 10{NBSP}%",
        "valid_to": "31 dic 2026",
    }


# ── A country by its name ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("write", "datum"), ON_A_COUNTRY)
@pytest.mark.parametrize(("language", "expected"), [("en", "Germany"), ("es", "Alemania")])
def test_a_write_says_the_country_by_its_name_never_its_code(write, datum, language, expected):
    """«Deactivate the beer rule in Germany» by voice: «País: Alemania», as the Rules screen's picker says it, never «DE».
    No person is needed: the name is the app's, not a record's."""
    card = assistant.card(get(write), {datum: "DE", "tax_category_key": "cerveza"}, language)
    assert {field["name"]: field["value"] for field in card["fields"]}[datum] == expected



@pytest.mark.parametrize(("language", "expected"), [("en", ["Germany", "France"]), ("es", ["Alemania", "Francia"])])
def test_a_batch_of_rules_says_the_country_of_each_one_by_its_name(language, expected):
    """«Create these two rules»: each line of the batch carries its country by its name, in the order sent."""
    rules = [
        {"country_code": "DE", "tax_category_key": "cerveza", "rate_pct": "19"},
        {"country_code": "FR", "tax_category_key": "vino", "rate_pct": "20"},
    ]
    (field,) = assistant.card(get("tax.rule.bulk_create"), {"rules": rules}, language)["fields"]
    assert [line["country_code"] for line in field["value"]] == expected

# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_RULE + ON_A_ROOT)
def test_a_rule_is_left_out_for_whoever_may_not_see_the_taxes(write, datum):
    """Whoever may not see Taxes (``tax.view``) is told no rule, never its id."""
    arguments = {datum: str(make_rule(make_category()).id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("tax.view"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_RULE + ON_A_ROOT)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_rule():
    """An automation's card (no person at hand) names no rule: nothing is read for anybody."""
    rule = make_rule(make_category())
    card = assistant.card(get("tax.rule.end"), {"id": str(rule.id), "valid_to": "2026-12-31"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"valid_to": "Dec 31, 2026"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_rule_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        rule = make_rule(make_category())
        for write, datum in ON_A_RULE + ON_A_ROOT:  # positive control
            assert datum in shown(write, {datum: str(rule.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, datum in ON_A_RULE + ON_A_ROOT:
            assert datum not in shown(write, {datum: str(rule.id)}, ctx=in_b), write


# ── The read that names a rule ────────────────────────────────────────────────────────────────────────────────────────


def test_the_read_that_names_a_rule_is_no_tool_route_nor_live_query():
    """``tax.rule.get`` exists for the card alone: the model and the screens read the rules by their list; so it is no
    tool of the assistant (``INTERNAL``) nor a route of the API."""
    read = registry["tax.rule.get"]
    assert (read.kind, read.permission, read.ai, read.expose_api) == ("query", "tax.view", INTERNAL, False)


@pytest.mark.django_db
def test_the_read_that_names_a_rule_finds_it_by_its_id_in_the_language_asked():
    """The rule as the list gives it, and its name in the language of whoever asks."""
    rule = make_rule(make_category(), country="DE", rate="19")
    read = get("tax.rule.get")
    found = read(ctx_for("hub_employee", language="es"), read.input(id=rule.id))
    assert (found.id, found.country_code, found.tax_category_key, found.rate_pct) == (
        rule.id,
        "DE",
        "drink.craft_beer",
        Decimal("19.00"),
    )
    assert found.label == f"Cervezas artesanas · Alemania · 19{NBSP}%"
    assert read(ctx_for(language="en"), read.input(id=rule.id)).label == "Cervezas artesanas · Germany · 19%"
    with pytest.raises(NotFound):
        read(ctx_for(), read.input(id=A_MISSING_ID))
