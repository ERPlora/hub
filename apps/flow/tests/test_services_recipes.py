"""Turning on, off, restoring and repairing the factory recipes the apps bring (WORKBOOK FLOW-F33 to F36;
the old Hub's HUB-F105 to F107 and its ``flow_template_activation_route.rs`` tests).

- **On** (``flow.recipe.enable``): the first time it builds the automation in the language of whoever turns
  it on, with **exactly** the permissions the recipe asks for — never more, whatever that person may do —
  and leaves it on, all in one transaction; afterwards it only switches the existing one on, keeping what
  the owner changed; one left with no permission at all gets the recipe's back. Twice is one automation.
- **Off** (``flow.recipe.disable``): a pause, never a delete: its permissions and its history stay.
- **Restore** (``flow.recipe.restore``): the same automation with today's recipe and exactly its
  permissions, on or paused as it was.
- **Repair** (``flow.recipe.repair``): one built from an older version gets only the «Only when…» clauses
  its app added since; its name, steps, permissions and switch stay.
"""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.flow import recipes
from apps.flow.models import Flow, FlowRun

from .conftest import ctx_for, make_run, run

pytestmark = pytest.mark.django_db

REF = "appointment/customer_cancelled"
TASK = "task.task.create"
ONLY_THE_CUSTOMER = {"input.by_customer": {"eq": True}}


def events(name: str) -> int:
    return OutboxEvent.objects.filter(name=name).count()


def built() -> Flow:
    return Flow.objects.get(recipe=REF, deleted_at__isnull=True)


# ── On (FLOW-F33) ────────────────────────────────────────────────────────────────────────────────────


def test_turning_a_recipe_on_builds_it_on_with_exactly_its_permissions():
    done = run("flow.recipe.enable", {"recipe": REF})
    assert done.created is True
    flow = built()
    assert (flow.name, flow.enabled, flow.grants) == ("Fill the gap when a customer cancels", True, [TASK])
    assert (flow.trigger_kind, flow.trigger_event, flow.trigger_filter) == (
        "event",
        "appointment.appointment.cancelled",
        ONLY_THE_CUSTOMER,
    )
    assert flow.steps == [
        {
            "id": "s1",
            "kind": "command",
            "operation": TASK,
            "params": {"title": "Fill the gap of appointment {{input.number}}", "priority": "high"},
        }
    ]
    assert (flow.recipe, flow.recipe_digest) == (REF, recipes.digest(recipes.find(REF)))
    assert done.flow.id == flow.id and done.flow.missing_grants == []
    assert [events(name) for name in ("flow.flow.created", "flow.flow.granted", "flow.flow.enabled")] == [1, 1, 1]


def test_it_is_built_in_the_language_of_whoever_turns_it_on():
    run("flow.recipe.enable", {"recipe": REF}, ctx_for(language="es"))
    flow = built()
    assert (flow.name, flow.language) == ("Cubrir el hueco cuando un cliente cancela", "es")
    assert flow.steps[0]["params"]["title"] == "Cubrir el hueco de la cita {{input.number}}"


def test_its_permissions_are_the_recipes_whatever_the_person_may_do():
    # An owner may do everything; the automation gets only what the recipe asks for (the old «never more»).
    owner = ctx_for("hub_owner")
    assert owner.has("customer.manage") and owner.has("sale.void_sale")
    run("flow.recipe.enable", {"recipe": REF}, owner)
    assert built().grants == [TASK]


def test_turning_it_on_twice_is_one_automation_and_says_it_found_it():
    first = run("flow.recipe.enable", {"recipe": REF})
    again = run("flow.recipe.enable", {"recipe": REF})
    assert (again.created, again.flow.id) == (False, first.flow.id)
    assert Flow.objects.filter(recipe=REF).count() == 1
    assert [events(name) for name in ("flow.flow.created", "flow.flow.granted", "flow.flow.enabled")] == [1, 1, 1]


def test_turning_it_back_on_keeps_what_the_owner_changed_and_the_permissions_they_retired():
    flow_id = run("flow.recipe.enable", {"recipe": REF}).flow.id
    mine = [{"id": "s1", "kind": "delay", "seconds": 3600}]
    run("flow.flow.update", {"id": str(flow_id), "name": "My gap", "steps": mine})
    run("flow.flow.grant", {"id": str(flow_id), "operations": ["customer.note.add"]})
    run("flow.recipe.disable", {"recipe": REF})

    again = run("flow.recipe.enable", {"recipe": REF})

    flow = built()
    assert (again.created, flow.enabled) == (False, True)
    assert (flow.name, flow.steps, flow.grants) == ("My gap", mine, ["customer.note.add"])


def test_one_left_with_no_permission_at_all_gets_the_recipes_back_when_turned_on():
    flow_id = run("flow.recipe.enable", {"recipe": REF}).flow.id
    run("flow.flow.grant", {"id": str(flow_id), "operations": []})
    run("flow.recipe.disable", {"recipe": REF})
    run("flow.recipe.enable", {"recipe": REF})
    assert (built().grants, built().enabled) == ([TASK], True)


def test_deleting_it_and_turning_it_on_again_brings_back_the_factory_recipe():
    flow_id = run("flow.recipe.enable", {"recipe": REF}).flow.id
    run("flow.flow.update", {"id": str(flow_id), "name": "My gap"})
    run("flow.flow.delete", {"id": str(flow_id)})
    again = run("flow.recipe.enable", {"recipe": REF})
    assert again.created is True and again.flow.id != flow_id
    assert built().name == "Fill the gap when a customer cancels"


def test_nobody_turns_on_a_recipe_asking_for_what_they_may_not_do_themselves():
    # Whoever manages automations but may not create tasks cannot have one create them (FLOW-F12's rule).
    clerk = ctx_for(permissions={"flow.view", "flow.manage"})
    with pytest.raises(PermissionDenied) as refused:
        run("flow.recipe.enable", {"recipe": REF}, clerk)
    assert refused.value.message == "You cannot allow what you may not do yourself: «task.task.create»."
    assert not Flow.objects.exists()


def test_a_recipe_set_aside_is_refused_with_its_reason_and_one_no_app_brings_is_not_found(monkeypatch):
    with pytest.raises(NotFound) as missing:
        run("flow.recipe.enable", {"recipe": "appointment/nothing"})
    assert missing.value.code == "flow.recipe_not_found"
    from apps.flow import queries

    active = {label: config for label, config in queries.active_apps().items() if label != "task"}
    monkeypatch.setattr(queries, "active_apps", lambda: active)
    with pytest.raises(Conflict) as aside:
        run("flow.recipe.enable", {"recipe": REF})
    assert (aside.value.code, aside.value.message) == (
        "flow.recipe_needs_apps",
        "It needs apps this business does not have: task.",
    )
    assert not Flow.objects.exists()


def test_a_reference_that_is_not_one_is_refused_by_field():
    from apps.flow.schemas import RecipeRefIn

    with pytest.raises(Exception):
        RecipeRefIn.model_validate({"recipe": "appointment"})
    with pytest.raises(Exception):
        RecipeRefIn.model_validate({"recipe": "Appointment/../x"})


def test_only_whoever_manages_automations_turns_recipes_on_off_restores_or_repairs():
    for name in ("flow.recipe.enable", "flow.recipe.disable", "flow.recipe.restore", "flow.recipe.repair"):
        with pytest.raises(PermissionDenied):
            run(name, {"recipe": REF}, ctx_for("hub_manager"))


# ── Off (FLOW-F34) ───────────────────────────────────────────────────────────────────────────────────


def test_turning_it_off_pauses_it_and_keeps_its_permissions_and_history():
    run("flow.recipe.enable", {"recipe": REF})
    make_run(built())
    paused = run("flow.recipe.disable", {"recipe": REF})
    flow = built()
    assert (paused.enabled, flow.enabled, flow.grants, flow.deleted_at) == (False, False, [TASK], None)
    assert FlowRun.objects.filter(flow=flow).count() == 1
    assert events("flow.flow.paused") == 1
    # Off twice changes nothing more.
    run("flow.recipe.disable", {"recipe": REF})
    assert events("flow.flow.paused") == 1


def test_turning_off_one_never_turned_on_or_deleted_is_a_not_found():
    with pytest.raises(NotFound) as never:
        run("flow.recipe.disable", {"recipe": REF})
    assert never.value.code == "flow.recipe_not_on"
    flow_id = run("flow.recipe.enable", {"recipe": REF}).flow.id
    run("flow.flow.delete", {"id": str(flow_id)})
    with pytest.raises(NotFound):
        run("flow.recipe.disable", {"recipe": REF})


# ── Restore (FLOW-F35) ───────────────────────────────────────────────────────────────────────────────


def owner_rewrote_it(enabled: bool = True) -> str:
    """The recipe turned on, then rewritten by the owner, with another permission, built from an older version."""
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}).flow.id)
    run(
        "flow.flow.update",
        {
            "id": flow_id,
            "name": "My gap",
            "trigger": {"kind": "event", "event": "appointment.appointment.cancelled"},
            "steps": [{"id": "s1", "kind": "command", "operation": "customer.note.add", "params": {"customer_id": "input.customer_id", "content": "Cancelled"}}],
        },
    )
    run("flow.flow.grant", {"id": flow_id, "operations": ["customer.note.add"]})
    if not enabled:
        run("flow.recipe.disable", {"recipe": REF})
    Flow.objects.filter(pk=flow_id).update(recipe_digest="0" * 64)
    return flow_id


def test_restoring_brings_todays_recipe_and_exactly_its_permissions_to_the_same_automation():
    flow_id = owner_rewrote_it()
    make_run(Flow.objects.get(pk=flow_id))
    version = Flow.objects.get(pk=flow_id).version

    restored = run("flow.recipe.restore", {"recipe": REF})

    flow = built()
    assert str(flow.id) == flow_id == str(restored.id)
    assert (flow.name, flow.trigger_filter, flow.grants, flow.enabled) == (
        "Fill the gap when a customer cancels",
        ONLY_THE_CUSTOMER,
        [TASK],
        True,
    )
    assert flow.steps[0]["operation"] == TASK
    assert flow.recipe_digest == recipes.digest(recipes.find(REF))
    assert flow.version == version + 1
    assert FlowRun.objects.filter(flow=flow).count() == 1  # its history stays


def test_restoring_a_paused_one_leaves_it_paused():
    owner_rewrote_it(enabled=False)
    run("flow.recipe.restore", {"recipe": REF})
    assert built().enabled is False


def test_restoring_one_never_turned_on_is_a_not_found():
    with pytest.raises(NotFound) as never:
        run("flow.recipe.restore", {"recipe": REF})
    assert never.value.code == "flow.recipe_not_on"


def test_restoring_asks_for_what_the_person_may_do_themselves():
    owner_rewrote_it()
    with pytest.raises(PermissionDenied):
        run("flow.recipe.restore", {"recipe": REF}, ctx_for(permissions={"flow.view", "flow.manage"}))
    assert built().name == "My gap"


# ── Repair (FLOW-F36) ────────────────────────────────────────────────────────────────────────────────


def built_from_an_older_version() -> str:
    """The recipe turned on, renamed and paused by the owner, as an older version left it: no «Only when…»."""
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}).flow.id)
    run("flow.flow.update", {"id": flow_id, "name": "My gap"})
    run("flow.recipe.disable", {"recipe": REF})
    Flow.objects.filter(pk=flow_id).update(trigger_filter={}, recipe_digest="0" * 64)
    return flow_id


def test_repairing_adds_only_the_clause_its_app_added_and_keeps_the_rest():
    flow_id = built_from_an_older_version()
    before = Flow.objects.get(pk=flow_id)
    updated = events("flow.flow.updated")

    run("flow.recipe.repair", {"recipe": REF})

    flow = built()
    assert flow.trigger_filter == ONLY_THE_CUSTOMER
    assert (flow.name, flow.steps, flow.grants, flow.enabled) == ("My gap", before.steps, before.grants, False)
    assert flow.version == before.version + 1
    assert flow.recipe_digest == "0" * 64  # repairing is not restoring: «New version» still says so
    assert events("flow.flow.updated") == updated + 1


def test_repairing_keeps_the_conditions_the_owner_added_and_only_adds_the_missing_one():
    flow_id = built_from_an_older_version()
    owners = {"input.staff_id": {"eq": "0199f0a0-0000-7000-8000-000000000001"}}
    Flow.objects.filter(pk=flow_id).update(trigger_filter=owners)

    run("flow.recipe.repair", {"recipe": REF})

    assert built().trigger_filter == {**owners, **ONLY_THE_CUSTOMER}


def test_repairing_what_has_nothing_to_repair_changes_nothing():
    run("flow.recipe.enable", {"recipe": REF})
    before = built()
    updated = events("flow.flow.updated")
    run("flow.recipe.repair", {"recipe": REF})
    assert (built().version, built().trigger_filter) == (before.version, before.trigger_filter)
    assert events("flow.flow.updated") == updated


def test_repairing_one_never_turned_on_is_a_not_found():
    with pytest.raises(NotFound) as never:
        run("flow.recipe.repair", {"recipe": REF})
    assert never.value.code == "flow.recipe_not_on"
