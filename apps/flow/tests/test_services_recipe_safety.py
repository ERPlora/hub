"""A factory recipe's safety fix reaches the automations already built from it, without waiting for the owner
(FIX-HUB-FLOW-FACTORY-SAFETY-FIX-WAITS-FOR-THE-OWNERS-UPDATE; WORKBOOK FLOW-F36, FLOW-F37, FLOW-F38, FLOW-F29).

The premise: the WhatsApp table answer turned on before its app fixed whose card its assistant acts for (hub#447,
``pinned``) was «New version», and nothing else: its assistant still chose ``on_behalf_of``, and after the yes another
guest's reservation was cancelled, until the owner pressed «Restore the factory one».

Now the data an app fixes on the «Ask the assistant» step of its recipe (``pinned``) are fixed on that step of every
automation built from it, whenever it was built: when the assistant is asked, when a change it proposed gets its yes
(also one proposed before the fix), when the automation is read (the editor shows them under «Fixed data») and when
it is copied. What the owner fixed themselves on that step stays (the assistant does not choose it either), and what
they changed of the rest of it is never touched. A recipe whose new version only rewords things changes nothing.

The market does the same with a safety fix that fits what the user changed: WordPress's automatic security releases,
Salesforce's enforced release updates, Zapier's automatic migration to a new app version, and Chrome and Android
applying a narrower permission without asking (a wider one waits for consent). The table is in the PR.
"""

import copy
import json
import uuid

import pytest
from live.context import system_context
from live.models import OutboxEvent

from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import TURN

from .conftest import A, ctx_for, run
from .test_recipes import declaration, declared  # noqa: F401 - the fixture
from .test_services_assistant_pinned import (  # noqa: F401 - the fixtures
    CANCEL,
    CHAT,
    MAY_CANCEL,
    UPDATE,
    gateway,
    guests,
    no_pauses,
    said,
    status_of,
    told,
    wants,
    worker,
)

pytestmark = pytest.mark.django_db

REF = "reservation/table"
#: What today's version fixes: whose card a change or a cancellation is, the one the run says.
THEIRS = {CANCEL: {"on_behalf_of": "input.customer"}, UPDATE: {"on_behalf_of": "input.customer"}}


def table(pinned: dict | None = None, prompt: str = "Help the guest {{input.name}}") -> dict:
    """A recipe whose «Ask the assistant» step (``s9``, «Ask me first») may cancel or change a reservation."""
    step = {"id": "s9", "kind": "assistant", "prompt": prompt, "tools": [CANCEL, UPDATE]}
    if pinned is not None:
        step["pinned"] = pinned
    grants = {CANCEL: "Cancels only the reservation of whoever writes.", UPDATE: "Changes only theirs."}
    return declaration(id="table", steps=[step], grants=grants)


def turned_on_before_the_fix(declared, older: dict | None = None) -> str:  # noqa: F811 - the fixture
    """The recipe turned on when its step fixed no data (or ``older``), and its app fixing them today: its id."""
    declared(("reservation", older or table()))
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner")).flow.id)
    declared(("reservation", table(pinned=THEIRS)))
    return flow_id


def stored(flow_id: str) -> Flow:
    return Flow.objects.get(pk=flow_id)


def read(flow_id: str):
    return run("flow.flow.detail", {"id": flow_id})


def asked(worker, gateway, flow_id: str, call: dict, data: dict, name: str = CANCEL) -> FlowRun:  # noqa: F811
    """A message reaches the automation and its assistant wants ``name`` with ``call``: the run as it is then."""
    gateway.reply(CHAT, json=wants(name, call))
    gateway.reply(CHAT, json=said("Done"))
    ran = worker.request("flow.flow.run", {"id": flow_id, "input": data})
    worker()
    return FlowRun.objects.get(pk=ran.id)


def yes(worker, ran: FlowRun) -> None:  # noqa: F811
    question = Question.objects.get(run_id=ran.id, status=Question.Status.PENDING)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL, actor="owner"))
    worker()


def shown_on_the_card(ran: FlowRun) -> dict:
    """``{datum: value}`` as «Waiting for your answer» shows the change ``ran`` waits on."""
    question = Question.objects.get(run_id=ran.id)
    [row] = [row for row in run("flow.question.list", {}, ctx_for(permissions=MAY_CANCEL)).rows if row.id == question.id]
    return {field["name"]: field["value"] for field in row.model_dump(mode="json")["fields"]}


def lucia_writes(guests) -> dict:  # noqa: F811
    return {"name": "Lucía", "customer": str(guests["lucia"].id)}


# ── Running it (FLOW-F38) ───────────────────────────────────────────────────────────────────────────────────────────


def test_one_turned_on_before_its_app_fixed_the_card_never_cancels_another_guest_s_table_after_the_yes(
    declared, gateway, worker, guests  # noqa: F811
):
    # The premise: on main the copy ran its old step, the assistant's on_behalf_of went through and the yes cancelled
    # Marta's table although Lucía was writing.
    flow_id = turned_on_before_the_fix(declared)
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}

    ran = asked(worker, gateway, flow_id, call, lucia_writes(guests))

    assert json.loads(ran.outputs[TURN]["proposal"]["arguments"])["on_behalf_of"] == str(guests["lucia"].id)
    yes(worker, ran)
    assert status_of(guests["other"]) == "pending"
    assert "reservation.customer_mismatch" in json.dumps(told(gateway))


def test_one_turned_on_before_the_fix_offers_the_assistant_its_tools_without_the_data_its_app_fixes(
    declared, gateway, worker, guests  # noqa: F811
):
    flow_id = turned_on_before_the_fix(declared)
    asked(worker, gateway, flow_id, {"id": str(guests["hers"].id)}, lucia_writes(guests))
    offered = {tool["name"]: tool["parameters"] for tool in gateway.sent(CHAT)[0].body["tools"]}
    for name in ("reservation__reservation__cancel", "reservation__reservation__update"):
        assert "on_behalf_of" not in offered[name]["properties"]
        assert "id" in offered[name]["properties"]


def test_their_own_table_is_still_cancelled_on_their_behalf(declared, gateway, worker, guests):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    ran = asked(worker, gateway, flow_id, {"id": str(guests["hers"].id)}, lucia_writes(guests))
    yes(worker, ran)
    assert status_of(guests["hers"]) == "cancelled"


def test_with_the_datum_empty_in_this_run_the_tool_is_not_used_never_the_old_way(declared, gateway, worker, guests):  # noqa: F811
    # Nobody's card in the run: the fixed datum is empty, so nothing waits for a yes and nothing is cancelled.
    flow_id = turned_on_before_the_fix(declared)
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}
    ran = asked(worker, gateway, flow_id, call, {"name": "Lucía"})
    assert not Question.objects.filter(run_id=ran.id).exists()
    assert status_of(guests["other"]) == "pending"
    assert json.loads(told(gateway)[0]["content"])["error"]["code"] == "flow.pinned_empty"


def test_a_change_proposed_before_the_fix_and_still_waiting_is_made_with_the_fixed_datum_at_the_yes(
    declared, gateway, worker, guests  # noqa: F811
):
    # The old step proposed it with Marta's card; the yes comes after the fix: never with what the assistant chose.
    declared(("reservation", table()))
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner")).flow.id)
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}
    ran = asked(worker, gateway, flow_id, call, lucia_writes(guests))
    assert json.loads(ran.outputs[TURN]["proposal"]["arguments"])["on_behalf_of"] == str(guests["marta"].id)
    declared(("reservation", table(pinned=THEIRS)))

    yes(worker, ran)

    assert status_of(guests["other"]) == "pending"
    assert "reservation.customer_mismatch" in json.dumps(told(gateway))


def test_the_card_of_a_change_waiting_from_before_says_on_whose_behalf_the_yes_makes_it(
    declared, gateway, worker, guests  # noqa: F811
):
    # FLOW-F29: the yes is given knowing what it does, never what the old step let the assistant choose.
    declared(("reservation", table()))
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner")).flow.id)
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}
    ran = asked(worker, gateway, flow_id, call, lucia_writes(guests))
    declared(("reservation", table(pinned=THEIRS)))

    assert shown_on_the_card(ran)["on_behalf_of"] == "Lucía Pérez"


def test_a_change_waiting_from_before_whose_fixed_datum_is_empty_now_is_not_made_at_the_yes(
    declared, gateway, worker, guests  # noqa: F811
):
    declared(("reservation", table()))
    flow_id = str(run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner")).flow.id)
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}
    ran = asked(worker, gateway, flow_id, call, {"name": "Lucía"})
    declared(("reservation", table(pinned=THEIRS)))
    # Its card no longer names whom the assistant chose: the yes will not make it on their behalf.
    assert "on_behalf_of" not in shown_on_the_card(ran)

    yes(worker, ran)

    assert status_of(guests["other"]) == "pending"
    assert json.loads(told(gateway)[0]["content"])["error"]["code"] == "flow.pinned_empty"
    entry = next(entry for entry in FlowRun.objects.get(pk=ran.id).log if entry["outcome"] == "assistant_pinned_empty")
    assert (entry["operation"], entry["fields"]) == (CANCEL, ["on_behalf_of"])


# ── What the owner changed stays ────────────────────────────────────────────────────────────────────────────────────


def test_what_the_owner_fixed_on_that_step_stays_and_the_rest_gets_its_app_s(declared, gateway, worker, guests):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    mine = {"id": "s9", "kind": "assistant", "prompt": "My words {{input.name}}", "tools": [CANCEL, UPDATE],
            "pinned": {CANCEL: {"on_behalf_of": "input.card"}}}
    run("flow.flow.update", {"id": flow_id, "steps": [mine]}, ctx_for("hub_owner"))

    [step] = read(flow_id).steps
    assert step["prompt"] == "My words {{input.name}}"
    assert step["pinned"] == {CANCEL: {"on_behalf_of": "input.card"}, UPDATE: THEIRS[UPDATE]}
    # The owner's own value is the one that goes: the assistant never chose it either.
    call = {"id": str(guests["hers"].id), "on_behalf_of": str(guests["marta"].id)}
    data = {"name": "Lucía", "card": str(guests["lucia"].id), "customer": str(guests["marta"].id)}
    ran = asked(worker, gateway, flow_id, call, data)
    assert json.loads(ran.outputs[TURN]["proposal"]["arguments"])["on_behalf_of"] == str(guests["lucia"].id)


def test_a_tool_the_owner_took_off_the_step_gets_nothing_and_their_words_stay(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    mine = {"id": "s9", "kind": "assistant", "prompt": "Only cancel {{input.name}}", "tools": [CANCEL]}
    run("flow.flow.update", {"id": flow_id, "steps": [mine]}, ctx_for("hub_owner"))

    [step] = read(flow_id).steps
    assert step == {**stored(flow_id).steps[0], "pinned": {CANCEL: THEIRS[CANCEL]}}
    assert step["prompt"] == "Only cancel {{input.name}}"


def test_a_step_the_owner_put_in_its_place_gets_nothing(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    mine = [{"id": "s1", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": [CANCEL]}]
    run("flow.flow.update", {"id": flow_id, "steps": mine}, ctx_for("hub_owner"))
    assert read(flow_id).steps == stored(flow_id).steps
    assert "pinned" not in stored(flow_id).steps[0]


def test_a_new_version_that_only_rewords_it_changes_nothing_and_says_nothing(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared, older=table(pinned=THEIRS, prompt="Help the customer {{input.name}}"))
    before = stored(flow_id)

    assert read(flow_id).steps == before.steps
    [row] = [row for row in run("flow.recipe.list", {}, ctx_for("hub_owner")).recipes if row.ref == REF]
    assert (row.installed.outdated, row.installed.repair, row.installed.enabled) == (True, {}, True)
    after = stored(flow_id)
    assert (after.version, after.steps, after.enabled) == (before.version, before.steps, True)


# ── Seeing it (FLOW-F36, FLOW-F37) ──────────────────────────────────────────────────────────────────────────────────


def test_it_is_read_with_the_data_its_app_fixes_and_nothing_waits_for_the_owner(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    [step] = read(flow_id).steps
    assert step["pinned"] == THEIRS
    assert "pinned" not in stored(flow_id).steps[0]  # read so, not written behind the owner's back
    [row] = [row for row in run("flow.recipe.list", {}, ctx_for("hub_owner")).recipes if row.ref == REF]
    assert (row.installed.outdated, row.installed.repair, row.installed.enabled) == (True, {}, True)


def test_updating_it_writes_the_fixed_data_and_keeps_its_name_permissions_and_switch(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    run("flow.flow.update", {"id": flow_id, "name": "My table"}, ctx_for("hub_owner"))
    before = stored(flow_id)
    updated = OutboxEvent.objects.filter(name="flow.flow.updated").count()

    run("flow.recipe.repair", {"recipe": REF}, ctx_for("hub_owner"))

    after = stored(flow_id)
    assert after.steps[0]["pinned"] == THEIRS
    assert (after.name, after.grants, after.enabled, after.trigger_filter) == (
        "My table", before.grants, True, before.trigger_filter
    )
    assert after.version == before.version + 1
    assert OutboxEvent.objects.filter(name="flow.flow.updated").count() == updated + 1


def test_a_copy_of_it_keeps_the_data_its_app_fixes(declared):  # noqa: F811
    flow_id = turned_on_before_the_fix(declared)
    copied = run("flow.flow.duplicate", {"id": flow_id}, ctx_for("hub_owner"))
    assert Flow.objects.get(pk=copied.id).recipe == ""
    assert Flow.objects.get(pk=copied.id).steps[0]["pinned"] == THEIRS


def test_an_automation_no_recipe_built_is_read_as_it_is(declared):  # noqa: F811
    declared(("reservation", table(pinned=THEIRS)))
    mine = [{"id": "s9", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": [CANCEL]}]
    flow_id = str(run("flow.flow.create", {"name": "Mine", "trigger": {"kind": "manual"}, "steps": mine}).id)
    assert read(flow_id).steps == stored(flow_id).steps
    assert "pinned" not in stored(flow_id).steps[0]


# ── The WhatsApp table answer, as it is on main ─────────────────────────────────────────────────────────────────────


def test_the_table_answer_turned_on_before_hub_447_is_read_with_its_card_and_number_fixed(monkeypatch):
    from apps.whatsapp_inbox import recipes as inbox_recipes

    today = {recipe["id"]: recipe for recipe in inbox_recipes.RECIPES}["reservation_from_whatsapp"]
    [fixed] = [step["pinned"] for step in today["steps"] if step["kind"] == "assistant"]
    older = copy.deepcopy(inbox_recipes.RECIPES)
    [table_answer] = [recipe for recipe in older if recipe["id"] == "reservation_from_whatsapp"]
    [step] = [step for step in table_answer["steps"] if step["kind"] == "assistant"]
    del step["pinned"]
    with monkeypatch.context() as patch:
        patch.setattr(inbox_recipes, "RECIPES", older)
        flow_id = str(run("flow.recipe.enable", {"recipe": "whatsapp_inbox/reservation_from_whatsapp"}, ctx_for("hub_owner")).flow.id)

    assert "pinned" not in next(step for step in stored(flow_id).steps if step["id"] == "s10")
    s10 = next(step for step in read(flow_id).steps if step["id"] == "s10")
    assert s10["pinned"] == fixed
    assert fixed[CANCEL] == {"on_behalf_of": "{{steps.s6.id}}{{steps.s7.id}}"}


# ── «Only when…»: a clause its app added since never waits for the owner either ─────────────────────────────────────

GAP = "appointment/gap"
CANCELLED = "appointment.appointment.cancelled"
ONLY_THE_CUSTOMER = {"input.by_customer": {"eq": True}}


def gap_turned_on_before_the_clause(declared) -> str:  # noqa: F811 - the fixture
    """The recipe «a cancelled appointment leaves a task» turned on when it started on every cancellation, and its app
    starting it only on the customer's today: its id."""
    declared(("appointment", declaration(trigger={"kind": "event", "event": CANCELLED})))
    flow_id = str(run("flow.recipe.enable", {"recipe": GAP}, ctx_for("hub_owner")).flow.id)
    declared(("appointment", declaration()))
    return flow_id


def starts(event: str, payload: dict) -> int:
    """How many automations ``event`` with ``payload`` starts, as the relay hands it over."""
    done = run("flow.run.react", {"event_id": str(uuid.uuid4()), "event": event, "payload": payload}, system_context(A))
    return done.started


def test_one_turned_on_before_its_app_left_out_the_team_s_cancellations_never_starts_on_one(declared):  # noqa: F811
    # The premise: on main it started on every cancellation until the owner pressed «Update it».
    flow_id = gap_turned_on_before_the_clause(declared)
    assert stored(flow_id).trigger_filter == {}
    assert starts(CANCELLED, {"by_customer": False, "number": "C-1"}) == 0
    assert starts(CANCELLED, {"by_customer": True, "number": "C-2"}) == 1
    assert stored(flow_id).trigger_filter == {}  # counted, not written behind the owner's back


def test_a_condition_the_owner_put_on_the_same_datum_is_theirs(declared):  # noqa: F811
    flow_id = gap_turned_on_before_the_clause(declared)
    theirs = {"input.by_customer": {"eq": False}}
    Flow.objects.filter(pk=flow_id).update(trigger_filter=theirs)
    assert starts(CANCELLED, {"by_customer": False, "number": "C-1"}) == 1
    assert starts(CANCELLED, {"by_customer": True, "number": "C-2"}) == 0
    assert read(flow_id).trigger["filter"] == theirs


def test_one_the_owner_made_start_on_something_else_gets_no_condition_of_its_recipe(declared):  # noqa: F811
    flow_id = gap_turned_on_before_the_clause(declared)
    Flow.objects.filter(pk=flow_id).update(trigger_event="appointment.appointment.created")
    assert read(flow_id).trigger["filter"] == {}
    assert starts("appointment.appointment.created", {"by_customer": False, "number": "C-1"}) == 1


def test_one_built_from_today_s_version_is_read_and_starts_as_it_is(declared):  # noqa: F811
    declared(("appointment", declaration()))
    flow_id = str(run("flow.recipe.enable", {"recipe": GAP}, ctx_for("hub_owner")).flow.id)
    before = stored(flow_id)
    assert read(flow_id).trigger["filter"] == before.trigger_filter == ONLY_THE_CUSTOMER
    assert starts(CANCELLED, {"by_customer": False, "number": "C-1"}) == 0
    assert starts(CANCELLED, {"by_customer": True, "number": "C-2"}) == 1
    assert (stored(flow_id).version, stored(flow_id).trigger_filter) == (before.version, before.trigger_filter)


def test_it_is_read_with_its_app_s_condition_and_a_copy_and_updating_it_write_it(declared):  # noqa: F811
    flow_id = gap_turned_on_before_the_clause(declared)
    assert read(flow_id).trigger["filter"] == ONLY_THE_CUSTOMER
    copied = run("flow.flow.duplicate", {"id": flow_id}, ctx_for("hub_owner"))
    assert Flow.objects.get(pk=copied.id).trigger_filter == ONLY_THE_CUSTOMER
    run("flow.recipe.repair", {"recipe": GAP}, ctx_for("hub_owner"))
    assert stored(flow_id).trigger_filter == ONLY_THE_CUSTOMER


def test_one_built_from_today_s_version_whose_condition_was_taken_off_still_never_starts_on_a_team_s_cancellation(
    declared,  # noqa: F811
):
    # Whenever it was built: its app's condition counts, as the data it fixes do (FLOW-F36).
    declared(("appointment", declaration()))
    flow_id = str(run("flow.recipe.enable", {"recipe": GAP}, ctx_for("hub_owner")).flow.id)
    Flow.objects.filter(pk=flow_id).update(trigger_filter={})
    assert starts(CANCELLED, {"by_customer": False, "number": "C-1"}) == 0


def test_the_table_answer_turned_on_before_its_app_left_out_old_messages_never_answers_one(monkeypatch):
    from apps.whatsapp_inbox import recipes as inbox_recipes

    older = copy.deepcopy(inbox_recipes.RECIPES)
    [table_answer] = [recipe for recipe in older if recipe["id"] == "reservation_from_whatsapp"]
    del table_answer["trigger"]["filter"]["input.source"]
    with monkeypatch.context() as patch:
        patch.setattr(inbox_recipes, "RECIPES", older)
        flow_id = str(run("flow.recipe.enable", {"recipe": "whatsapp_inbox/reservation_from_whatsapp"}, ctx_for("hub_owner")).flow.id)
    assert "input.source" not in stored(flow_id).trigger_filter

    message = {"id": str(uuid.uuid4()), "direction": "inbound", "source": "history", "phone": "+34600111222"}
    assert starts("whatsapp_inbox.message.received", message) == 0
    assert read(flow_id).trigger["filter"]["input.source"] == {"eq": "live"}
