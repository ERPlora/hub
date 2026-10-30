"""The factory recipes of the apps (WORKBOOK FLOW-F33 to F36; the old Hub's HUB-F104 and its
``crates/runtime/src/flows/templates.rs``): what ``apps.flow.recipes`` reads from each active app's
``recipes.py`` and offers, and what it sets aside, with why.

A recipe is data its app declares (``RECIPES``): an id, its words, its trigger, its steps and the
permissions it asks for, each with the sentence its app wrote. Automations offers it only when this
business has what it names and when it asks for exactly the permissions its steps use, never more; the
rest is set aside with its reason and the others are still offered. Its fingerprint is what it does —
its document in every language and its permissions —, never the sentences that explain it.
"""

import pytest
from django.utils.translation import gettext_lazy as _

from apps.flow import queries, recipes

from .conftest import make_flow

pytestmark = pytest.mark.django_db

TASK = "task.task.create"
DAY = "reservation.availability.day"


def declaration(**more) -> dict:
    """A recipe as an app declares it: a cancelled appointment leaves a task (lazy words, as in a recipes.py)."""
    declared = {
        "id": "gap",
        "name": _("Untitled automation"),
        "summary": "Leaves a task when a customer cancels.",
        "description": "When a customer cancels, it leaves you a task to fill the gap.",
        "trigger": {
            "kind": "event",
            "event": "appointment.appointment.cancelled",
            "filter": {"input.by_customer": {"eq": True}},
        },
        "steps": [
            {
                "id": "s1",
                "kind": "command",
                "operation": TASK,
                "params": {"title": "Fill the gap of {{input.number}}", "priority": "high"},
            }
        ],
        "grants": {TASK: "Leaves you the task."},
    }
    declared.update(more)
    return declared


def asking(*tools: str, before: tuple[dict, ...] = ()) -> dict:
    """A recipe whose «Ask the assistant» step may use ``tools``, after the steps ``before``; it asks for exactly
    the permissions they use."""
    steps = [*before, {"id": "s9", "kind": "assistant", "prompt": "Offer the customer another day.", "tools": list(tools)}]
    names = [step["operation"] for step in before] + list(tools)
    return declaration(id="ask", steps=steps, grants={name: "Looks it up." for name in names})


@pytest.fixture
def declared(monkeypatch):
    """``declared(*declarations)``: what the apps declare, instead of their recipes.py (by app label)."""

    def plant(*found: tuple[str, dict]) -> None:
        apps = queries.active_apps()
        monkeypatch.setattr(
            recipes, "declarations", lambda: [(apps[label], recipe) for label, recipe in found]
        )

    return plant


def without(monkeypatch, *labels: str) -> None:
    """This business without the apps ``labels``."""
    active = {label: config for label, config in queries.active_apps().items() if label not in labels}
    monkeypatch.setattr(queries, "active_apps", lambda: active)


# ── What the apps bring ──────────────────────────────────────────────────────────────────────────────


def test_an_app_brings_its_recipes_and_automations_offers_them(declared):
    declared(("appointment", declaration()))
    offered, set_aside = recipes.shelf()
    assert [(recipe.app.label, recipe.id, recipe.ref) for recipe in offered] == [
        ("appointment", "gap", "appointment/gap")
    ]
    assert set_aside == []


def test_the_apps_recipes_py_is_where_they_come_from():
    # The real ones: an app declares its RECIPES in its own recipes.py; an app without one brings none.
    found = {(config.label, recipe["id"]) for config, recipe in recipes.declarations()}
    assert ("appointment", "customer_cancelled") in found
    assert ("online_booking", "booked_online") in found
    assert not any(label == "customer" for label, _ in found)


def test_every_recipe_the_apps_bring_is_offered():
    # Guard: a recipe an app ships that this business cannot offer with every app on is a bug of that app.
    offered, set_aside = recipes.shelf()
    assert [(item.ref, item.code, item.message) for item in set_aside] == []
    assert {recipe.ref for recipe in offered} >= {"appointment/customer_cancelled", "online_booking/booked_online"}


def test_a_recipe_is_built_in_the_language_it_is_asked_in():
    recipe = recipes.find("appointment/customer_cancelled")
    english, spanish = recipes.build(recipe, "en"), recipes.build(recipe, "es")
    assert english["name"] == "Fill the gap when a customer cancels"
    assert spanish["name"] == "Cubrir el hueco cuando un cliente cancela"
    assert spanish["steps"][0]["params"]["title"] == "Cubrir el hueco de la cita {{input.number}}"
    assert english["trigger"] == spanish["trigger"] == {
        "kind": "event",
        "event": "appointment.appointment.cancelled",
        "filter": {"input.by_customer": {"eq": True}},
    }
    assert recipes.grants(recipe) == [TASK]
    assert recipes.reasons(recipe, "es")[TASK].startswith("Te deja la tarea")


def test_finding_one_no_app_brings_is_a_not_found_and_one_set_aside_says_why(declared):
    from live.errors import Conflict, NotFound

    declared(("appointment", declaration()), ("appointment", declaration(id="wide", grants={})))
    with pytest.raises(NotFound) as missing:
        recipes.find("appointment/nothing")
    assert missing.value.code == "flow.recipe_not_found"
    with pytest.raises(Conflict) as aside:
        recipes.find("appointment/wide")
    assert aside.value.code == "flow.recipe_invalid"


# ── What is set aside, and why ───────────────────────────────────────────────────────────────────────


def test_a_recipe_that_needs_an_app_this_business_does_not_have_is_set_aside_naming_it(declared, monkeypatch):
    declared(("appointment", declaration()))
    without(monkeypatch, "task")
    offered, set_aside = recipes.shelf()
    assert offered == []
    assert [(item.ref, item.code, item.apps) for item in set_aside] == [
        ("appointment/gap", "flow.recipe_needs_apps", ("task",))
    ]


def test_a_recipe_whose_assistant_uses_a_tool_of_an_app_this_business_does_not_have_is_set_aside_naming_it(
    declared, monkeypatch
):
    # FLOW-F33: its only reference to Reservations is a tool of «Ask the assistant»; the gallery says which app
    # to turn on, never «it is wrong».
    declared(("appointment", asking(DAY)))
    without(monkeypatch, "reservation")
    offered, set_aside = recipes.shelf()
    assert offered == []
    assert [(item.ref, item.code, item.apps, item.message) for item in set_aside] == [
        (
            "appointment/ask",
            "flow.recipe_needs_apps",
            ("reservation",),
            "It needs apps this business does not have: reservation.",
        )
    ]


def test_with_that_app_on_the_recipe_whose_assistant_uses_its_tool_is_offered(declared):
    declared(("appointment", asking(DAY)))
    offered, set_aside = recipes.shelf()
    assert [recipe.ref for recipe in offered] == ["appointment/ask"]
    assert set_aside == []


def test_an_app_named_by_a_step_and_by_a_tool_is_needed_once(declared, monkeypatch):
    get = {"id": "s1", "kind": "query", "operation": "reservation.reservation.get", "params": {"id": "input.id"}}
    declared(("appointment", asking(DAY, before=(get,))))
    without(monkeypatch, "reservation", "task")
    _, set_aside = recipes.shelf()
    assert [(item.code, item.apps) for item in set_aside] == [("flow.recipe_needs_apps", ("reservation",))]


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        # The platform's own tools are no app to turn on.
        ("assistant", "base.profile.update"),
        # Nor this app's own: Automations is on, it is reading the recipe.
        ("assistant", "flow.flow.list"),
        ("query", "flow.flow.list"),
    ],
)
def test_a_name_of_no_app_this_business_can_turn_on_needs_no_app_and_is_set_aside_naming_it(declared, kind, name):
    if kind == "assistant":
        step = {"id": "s9", "kind": "assistant", "prompt": "Do it.", "tools": [name]}
    else:
        step = {"id": "s1", "kind": "query", "operation": name, "params": {}}
    declared(("appointment", declaration(steps=[step], grants={name: "Looks it up."})))
    _, set_aside = recipes.shelf()
    assert [(item.code, item.apps, item.message) for item in set_aside] == [
        ("flow.recipe_invalid", (), f"That action does not exist in this business: «{name}».")
    ]


def test_the_recipes_of_an_app_that_is_off_are_not_offered_at_all(monkeypatch):
    without(monkeypatch, "appointment")
    offered, set_aside = recipes.shelf()
    assert not any(recipe.app.label == "appointment" for recipe in offered)
    assert not any(item.app.label == "appointment" for item in set_aside)


def test_a_recipe_asking_for_a_permission_its_steps_do_not_use_is_set_aside(declared):
    declared(("appointment", declaration(grants={TASK: "x", "customer.note.add": "y"})))
    offered, set_aside = recipes.shelf()
    assert offered == []
    assert [(item.code, item.message) for item in set_aside] == [
        ("flow.recipe_invalid", "It asks for permissions its steps do not use: «customer.note.add».")
    ]


def test_a_recipe_whose_steps_use_a_permission_it_does_not_ask_for_is_set_aside(declared):
    declared(("appointment", declaration(grants={})))
    _, set_aside = recipes.shelf()
    assert [(item.code, item.message) for item in set_aside] == [
        ("flow.recipe_invalid", "Its steps use permissions it does not ask for: «task.task.create».")
    ]


def test_a_recipe_with_an_action_that_needs_a_person_is_set_aside(declared):
    void = {"id": "s1", "kind": "command", "operation": "sale.order.void", "params": {"order_id": "input.id"}}
    declared(("appointment", declaration(steps=[void], grants={"sale.order.void": "Voids it."})))
    _, set_aside = recipes.shelf()
    assert [(item.code, item.message) for item in set_aside] == [
        ("flow.recipe_invalid", "«sale.order.void» needs a person in front: an automation cannot do it.")
    ]


def test_a_recipe_that_does_not_read_as_an_automation_is_set_aside_and_the_others_still_offered(declared):
    broken = declaration(id="broken", steps=[{"id": "s1", "kind": "teleport"}])
    nameless = {"id": "nameless"}
    declared(("appointment", broken), ("appointment", nameless), ("appointment", declaration()))
    offered, set_aside = recipes.shelf()
    assert [recipe.ref for recipe in offered] == ["appointment/gap"]
    assert [(item.ref, item.code) for item in set_aside] == [
        ("appointment/broken", "flow.recipe_invalid"),
        ("appointment/nameless", "flow.recipe_invalid"),
    ]


def test_two_recipes_with_the_same_id_in_one_app_keep_the_first_and_set_the_other_aside(declared):
    declared(("appointment", declaration()), ("appointment", declaration(summary="Another one.")))
    offered, set_aside = recipes.shelf()
    assert [recipe.ref for recipe in offered] == ["appointment/gap"]
    assert [(item.ref, item.code) for item in set_aside] == [("appointment/gap", "flow.recipe_invalid")]


# ── The fingerprint: what it does, never how it is explained (hub#2059) ──────────────────────────────


def test_the_same_recipe_always_has_the_same_fingerprint(declared):
    declared(("appointment", declaration()))
    recipe = recipes.find("appointment/gap")
    assert recipes.digest(recipe) == recipes.digest(recipes.find("appointment/gap"))
    assert len(recipes.digest(recipe)) == 64


def test_other_words_in_its_steps_or_its_name_are_another_recipe(declared):
    declared(("appointment", declaration()))
    before = recipes.digest(recipes.find("appointment/gap"))
    reworded = declaration()
    reworded["steps"][0]["params"]["title"] = "Fill the hole of {{input.number}}"
    declared(("appointment", reworded))
    assert recipes.digest(recipes.find("appointment/gap")) != before
    declared(("appointment", declaration(name="Fill the gap")))
    assert recipes.digest(recipes.find("appointment/gap")) != before


def test_another_permission_or_trigger_is_another_recipe(declared):
    declared(("appointment", declaration()))
    before = recipes.digest(recipes.find("appointment/gap"))
    declared(("appointment", declaration(trigger={"kind": "event", "event": "appointment.appointment.cancelled"})))
    assert recipes.digest(recipes.find("appointment/gap")) != before


def test_rewording_its_summary_or_a_permissions_sentence_is_not_another_recipe(declared):
    declared(("appointment", declaration()))
    before = recipes.digest(recipes.find("appointment/gap"))
    declared(("appointment", declaration(summary="Other words.", description="More words.", grants={TASK: "New."})))
    assert recipes.digest(recipes.find("appointment/gap")) == before


# ── A fault its app already fixed (FLOW-F36) ─────────────────────────────────────────────────────────


def test_an_automation_built_from_an_older_version_lacks_the_clauses_its_app_added(declared):
    declared(("appointment", declaration()))
    recipe = recipes.find("appointment/gap")
    older = make_flow(
        trigger_event="appointment.appointment.cancelled",
        trigger_filter={},
        recipe="appointment/gap",
        recipe_digest="0" * 64,
    )
    assert recipes.missing_clauses(recipe, older) == {"input.by_customer": {"eq": True}}


def test_nothing_to_repair_when_it_has_the_clauses_or_was_built_from_this_version_or_starts_otherwise(declared):
    declared(("appointment", declaration()))
    recipe = recipes.find("appointment/gap")
    current = recipes.digest(recipe)
    event = "appointment.appointment.cancelled"
    # Built from today's version: whatever the owner left out was their choice, not a fault.
    assert recipes.missing_clauses(recipe, make_flow(trigger_event=event, trigger_filter={}, recipe_digest=current)) == {}
    # It already has the clause (the owner's own value of it is kept: only a missing clause is a fault).
    narrowed = {"input.by_customer": {"eq": False}}
    older = make_flow(trigger_event=event, trigger_filter=narrowed, recipe_digest="0" * 64)
    assert recipes.missing_clauses(recipe, older) == {}
    # The owner made it start on something else: not the recipe's trigger any more.
    other = make_flow(trigger_event="appointment.appointment.created", trigger_filter={}, recipe_digest="0" * 64)
    assert recipes.missing_clauses(recipe, other) == {}
