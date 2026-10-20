"""Read operations of the flow app: the catalog of events and actions of the active apps, the list and
detail of the automations, their runs, the assistant's drafts, «is it already set up?», the last real
event of a kind, and «Try it», which walks an automation against that event and executes nothing."""

import datetime as dt
import json
import uuid

import pytest
from django.utils import timezone, translation
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.flow import queries
from apps.flow.models import Draft, Flow, FlowRun
from apps.task.models import Task

from .conftest import A, B, TASK_STEP, ctx_for, make_draft, make_flow, make_run, run

pytestmark = pytest.mark.django_db


def outbox(name: str, payload: dict, scope=A, **fields) -> OutboxEvent:
    return OutboxEvent.objects.create(
        scope_kind=scope.kind, scope_key=scope.key, name=name, payload=payload, **fields
    )


# The catalog: only what the active apps declare, never a made-up name


def test_the_catalog_lists_the_events_of_the_active_apps_but_its_own():
    catalog = run("flow.catalog.read")
    names = {event.name for event in catalog.events}
    assert {
        "customer.customer.created",
        "sale.sale.completed",
        "task.task.completed",
    } <= names
    assert not any(name.startswith("flow.") for name in names)
    created = next(
        event for event in catalog.events if event.name == "customer.customer.created"
    )
    assert (created.app, created.app_name) == ("customer", "Customers")


def test_an_event_an_app_lists_in_another_apps_name_stays_out_of_the_catalog(monkeypatch):
    from apps.customer import events as customer_events

    monkeypatch.setattr(customer_events, "ALL", [*customer_events.ALL, "ghost.thing.happened"])
    names = {event.name for event in run("flow.catalog.read").events}
    assert "customer.customer.created" in names
    assert "ghost.thing.happened" not in names


def test_the_catalog_names_the_apps_in_the_callers_language():
    with translation.override("es"):
        catalog = run("flow.catalog.read", ctx=ctx_for(language="es"))
    created = next(
        event for event in catalog.events if event.name == "customer.customer.created"
    )
    assert created.app_name == "Clientes"


def test_the_catalog_offers_the_actions_and_reads_a_person_can_be_granted():
    actions = {action.name: action for action in run("flow.catalog.read").actions}
    create = actions["task.task.create"]
    assert (create.kind, create.app, create.app_name) == ("command", "task", "Tasks")
    assert create.description.startswith("Create a task")
    fields = {field.name: field for field in create.fields}
    assert fields["title"].required is True and fields["title"].type == "string"
    assert fields["title"].description == "What has to be done, in a short sentence."
    assert fields["priority"].choices == ["low", "medium", "high", "urgent"]
    assert {"id", "number", "title"} <= set(create.outputs)
    assert actions["customer.customer.detail"].kind == "query"
    # A read leaves found and count, and the first row's fields of a list.
    listed = actions["customer.customer.list"]
    assert {"found", "count", "name"} <= set(listed.outputs)
    # Platform-only reactions and the automations themselves are never offered.
    assert "task.task.release_member" not in actions
    assert not any(name.startswith("flow.") for name in actions)


def test_an_app_that_is_not_active_is_not_in_the_catalog(monkeypatch):
    active = {
        label: config
        for label, config in queries.active_apps().items()
        if label != "task"
    }
    monkeypatch.setattr(queries, "active_apps", lambda: active)
    catalog = run("flow.catalog.read")
    assert not any(event.app == "task" for event in catalog.events)
    assert not any(action.app == "task" for action in catalog.actions)


def test_the_catalog_needs_view():
    with pytest.raises(PermissionDenied):
        run("flow.catalog.read", ctx=ctx_for("hub_manager"))


# The list


def test_the_list_shows_every_automation_with_its_trigger_and_last_run():
    welcome = make_flow("Welcome")
    weekly = make_flow(
        "Weekly review",
        trigger_kind=Flow.Trigger.SCHEDULE,
        schedule={"every": "week", "weekday": 4, "time": "18:00"},
        enabled=False,
    )
    make_run(welcome, status=FlowRun.Status.FAILED)
    page = run("flow.flow.list", {"sort": "name"})
    assert page.total == 2
    assert [row.id for row in page.rows] == [weekly.id, welcome.id]
    first, second = page.rows
    assert first.trigger == {
        "kind": "schedule",
        "every": "week",
        "weekday": 4,
        "day": None,
        "time": "18:00",
    }
    assert first.last_run is None
    assert second.trigger == {
        "kind": "event",
        "event": "customer.customer.created",
        "filter": {},
    }
    assert second.last_run.status == "failed"


def test_the_list_searches_the_name_the_event_and_the_actions():
    make_flow("Welcome")
    make_flow(
        "Cash close", trigger_event="cash_register.session.closed", steps=[], grants=[]
    )
    queries_ = {
        "welc": ["Welcome"],
        "cash_register": ["Cash close"],
        "task.task.create": ["Welcome"],
        "nothing": [],
    }
    from apps.flow.services import refresh_search_text

    for flow in Flow.objects.all():
        refresh_search_text(flow)
        flow.save(update_fields=["search_text"])
    for text, names in queries_.items():
        assert [
            row.name for row in run("flow.flow.list", {"search": text}).rows
        ] == names, text


def test_the_list_filters_by_state_and_trigger_and_hides_the_deleted():
    make_flow("On")
    make_flow("Paused", enabled=False)
    make_flow("By hand", trigger_kind=Flow.Trigger.MANUAL)
    make_flow("Gone", deleted_at=timezone.now())
    names = lambda data: sorted(row.name for row in run("flow.flow.list", data).rows)  # noqa: E731
    assert names({}) == ["By hand", "On", "Paused"]
    assert names({"enabled": False}) == ["Paused"]
    assert names({"trigger_kind": "manual"}) == ["By hand"]


def test_the_list_pages_with_a_stable_order():
    for n in range(5):
        make_flow(f"F{n}")
    first = run("flow.flow.list", {"limit": 2, "sort": "name"})
    second = run("flow.flow.list", {"limit": 2, "offset": 2, "sort": "name"})
    assert (first.total, [row.name for row in first.rows + second.rows]) == (
        5,
        ["F0", "F1", "F2", "F3"],
    )


def test_reading_needs_the_view_permission():
    for name in ("flow.flow.list", "flow.draft.list"):
        with pytest.raises(PermissionDenied):
            run(name, {}, ctx_for("hub_employee"))


# One automation


def test_the_detail_says_what_it_needs_and_what_it_lacks():
    flow = make_flow(
        steps=[
            TASK_STEP,
            {
                "id": "s2",
                "kind": "query",
                "operation": "customer.customer.detail",
                "params": {},
            },
        ],
        grants=["task.task.create"],
    )
    detail = run("flow.flow.detail", {"id": str(flow.id)})
    assert detail.required_grants == ["task.task.create", "customer.customer.detail"]
    assert detail.missing_grants == ["customer.customer.detail"]
    assert detail.steps[1]["operation"] == "customer.customer.detail"


def test_an_automation_is_found_by_its_name_or_part_of_it():
    flow = make_flow("Welcome a new customer")
    make_flow("Cash close")
    assert run("flow.flow.detail", {"flow": "welcome"}).id == flow.id
    assert run("flow.flow.detail", {"flow": "Welcome a new customer"}).id == flow.id


def test_a_name_that_fits_several_says_which():
    make_flow("Welcome A")
    make_flow("Welcome B")
    with pytest.raises(Conflict) as refused:
        run("flow.flow.detail", {"flow": "welcome"})
    assert refused.value.code == "flow.ambiguous_flow"
    assert "Welcome A" in refused.value.message and "Welcome B" in refused.value.message


def test_an_unknown_or_deleted_automation_does_not_exist():
    gone = make_flow(deleted_at=timezone.now())
    for data in (
        {"id": str(gone.id)},
        {"id": str(uuid.uuid7())},
        {"flow": "nothing like it"},
    ):
        with pytest.raises(NotFound) as missing:
            run("flow.flow.detail", data)
        assert (
            missing.value.message == "That automation does not exist in this business."
        )


# Its runs


def test_the_runs_newest_first_with_how_many_failed():
    flow = make_flow()
    older = make_run(
        flow,
        status=FlowRun.Status.FAILED,
        started_at=timezone.now() - dt.timedelta(hours=1),
    )
    newer = make_run(flow, status=FlowRun.Status.SUCCEEDED)
    make_run(make_flow("Other"), status=FlowRun.Status.FAILED)
    page = run("flow.run.list", {"flow_id": str(flow.id)})
    assert [row.id for row in page.rows] == [newer.id, older.id]
    assert (page.total, page.failed, page.limit) == (2, 1, 20)
    assert page.rows[0].steps_total == 1
    only_failed = run("flow.run.list", {"flow_id": str(flow.id), "status": "failed"})
    assert [row.id for row in only_failed.rows] == [older.id]


# Drafts


def test_the_drafts_waiting_newest_first():
    make_draft("Used", status=Draft.Status.USED)
    first = make_draft("First")
    second = make_draft("Second")
    page = run("flow.draft.list")
    assert [row.id for row in page.rows] == [second.id, first.id]
    assert page.rows[0].definition["steps"][0]["operation"] == "task.task.create"


# «Is it already set up here?» (FLOW-F20)


def test_the_status_counts_the_set_up_the_on_and_the_half_built():
    make_flow("On")
    make_flow("Paused", enabled=False)
    make_flow("Half built", grants=[])
    make_flow("Other event", trigger_event="sale.sale.completed")
    make_flow("Gone", deleted_at=timezone.now())
    make_flow("Other action", grants=["customer.note.add"])
    status = run(
        "flow.flow.status",
        {"event": "customer.customer.created", "operation": "task.task.create"},
    )
    assert (status.total, status.enabled, status.unfinished) == (2, 1, 1)


# The last real event of a kind


def test_the_sample_is_the_newest_event_of_this_business():
    outbox(
        "sale.sale.completed",
        {"total": 100},
        created_at=timezone.now() - dt.timedelta(hours=2),
    )
    newest = outbox("sale.sale.completed", {"total": 250})
    outbox("sale.sale.completed", {"total": 999}, scope=B)
    sample = run("flow.event.sample", {"event": "sale.sale.completed"})
    assert (sample.found, sample.payload, sample.at) == (
        True,
        {"total": 250},
        newest.created_at,
    )
    nothing = run("flow.event.sample", {"event": "task.task.created"})
    assert (nothing.found, nothing.payload, nothing.at) == (False, {}, None)


def test_the_sample_of_a_real_customer_carries_no_personal_data():
    # hub#826, hub#2525: the example beside each datum is what the event brought, and an event brings
    # ids, never a customer's name, city or notes (the real Customers app, not a hand-made outbox row).
    created = run(
        "customer.customer.create",
        {"name": "Berta Segunda", "city": "Madrid", "notes": "Allergic to latex"},
    )
    sample = run("flow.event.sample", {"event": "customer.customer.created"})
    assert sample.payload == {"id": str(created.id)}
    assert "Berta" not in json.dumps(sample.payload)


def test_the_sample_needs_manage():
    with pytest.raises(PermissionDenied):
        run(
            "flow.event.sample",
            {"event": "sale.sale.completed"},
            ctx_for(permissions={"flow.view"}),
        )


# «Try it»: what it would do with the last real event, executing nothing (FLOW-F13)

def try_(document: dict, flow=None):
    """«Try it» on ``document`` (the editor's, saved or not), with ``flow``'s permissions when given."""
    data = {"document": json.dumps(document)}
    if flow is not None:
        data["id"] = str(flow.id)
    return run("flow.flow.test", data)


BIG_SALE = {
    "trigger": {
        "kind": "event",
        "event": "sale.sale.completed",
        "filter": {"input.total": {"gte": 10000}},
    },
    "steps": [
        {
            "id": "s1",
            "kind": "condition",
            "when": {"input.customer_id": {"exists": True}},
        },
        {"id": "s2", "kind": "delay", "seconds": 3600},
        {
            "id": "s3",
            "kind": "command",
            "operation": "task.task.create",
            "params": {
                "title": "Thank {{input.customer_name}}",
                "description": "input.note",
            },
        },
        {
            "id": "s4",
            "kind": "command",
            "operation": "task.task.create",
            "params": {"title": "steps.s3.number"},
        },
    ],
}


def test_try_walks_the_steps_against_the_last_real_event_and_executes_nothing():
    flow = make_flow(grants=["task.task.create"])
    outbox(
        "sale.sale.completed",
        {"total": 12500, "customer_id": "c-1", "customer_name": "Ana"},
    )
    result = try_(BIG_SALE, flow)
    assert result.sample.found is True
    assert (result.starts, result.trigger_failed) == (True, [])
    condition, wait, task, second = result.steps
    assert condition.outcome == "would_run"
    assert (wait.outcome, wait.seconds) == ("waits", 3600)
    assert task.outcome == "would_run"
    assert task.params == {"title": "Thank Ana"}
    assert task.empty == ["description"]
    assert second.outcome == "cannot_tell"
    assert second.unknown == ["title"]
    assert Task.objects.count() == 0
    assert FlowRun.objects.count() == 0


def test_try_says_when_it_would_not_even_start_or_stop_at_a_condition():
    outbox("sale.sale.completed", {"total": 500})
    result = try_(BIG_SALE)
    assert result.starts is False
    assert [clause.path for clause in result.trigger_failed] == ["input.total"]
    outbox("sale.sale.completed", {"total": 20000})
    result = try_(BIG_SALE)
    assert result.starts is True
    assert result.steps[0].outcome == "stops_here"
    assert [clause.path for clause in result.steps[0].failed] == ["input.customer_id"]
    assert [step.outcome for step in result.steps[1:]] == ["not_reached"] * 3


def test_try_says_what_the_action_would_refuse_and_what_it_is_not_allowed():
    outbox("sale.sale.completed", {"total": 20000, "customer_id": "c-1"})
    document = BIG_SALE | {
        "steps": [
            {
                "id": "s1",
                "kind": "command",
                "operation": "task.task.create",
                "params": {"priority": "soon"},
            }
        ]
    }
    result = try_(document)
    (step,) = result.steps
    assert step.outcome == "not_allowed"
    flow = make_flow(grants=["task.task.create"])
    (step,) = try_(document, flow).steps
    assert step.outcome == "refused"
    assert set(step.errors) == {"title", "priority"}


def test_try_says_an_action_of_an_app_that_is_not_here_is_unavailable(monkeypatch):
    active = {
        label: config
        for label, config in queries.active_apps().items()
        if label != "task"
    }
    monkeypatch.setattr(queries, "active_apps", lambda: active)
    outbox("sale.sale.completed", {"total": 20000})
    document = {"trigger": {"kind": "manual"}, "steps": [TASK_STEP]}
    assert try_(document).steps[0].outcome == "unavailable"


def test_try_without_an_event_walks_with_nothing_in():
    result = try_({"trigger": {"kind": "manual"}, "steps": [TASK_STEP]})
    assert (result.sample.found, result.starts) == (False, True)
    assert result.steps[0].outcome == "not_allowed"


def test_queries_never_write():
    flow = make_flow()
    before = (
        Flow.objects.count(),
        FlowRun.objects.count(),
        OutboxEvent.objects.count(),
    )
    run("flow.flow.list")
    run("flow.flow.detail", {"id": str(flow.id)})
    try_({"trigger": {"kind": "manual"}, "steps": [TASK_STEP]})
    assert (
        Flow.objects.count(),
        FlowRun.objects.count(),
        OutboxEvent.objects.count(),
    ) == before


def test_the_system_context_reads_everything():
    make_flow()
    assert run("flow.flow.list", {}, system_context(A)).total == 1


# What needs a person in front is never offered (review 2026-10-15, item 1)


def test_the_catalog_never_offers_an_action_that_needs_a_person():
    actions = {action.name for action in run("flow.catalog.read").actions}
    for name in (
        "sale.order.void",
        "sale.sale.void",
        "sale.sale.refund",
        "customer.customer.erase",
        "verifactu.record.transmit",
        "verifactu.record.cancel",
    ):
        assert name not in actions, name
    assert {"task.task.create", "customer.note.add"} <= actions


def test_try_says_an_action_that_needs_a_person_is_not_for_automations():
    flow = make_flow(grants=["sale.order.void"])
    document = {
        "trigger": {"kind": "manual"},
        "steps": [{"id": "s1", "kind": "command", "operation": "sale.order.void", "params": {}}],
    }
    assert try_(document, flow).steps[0].outcome == "high_risk"
