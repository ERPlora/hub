"""Write operations of the flow app: create, change, turn on and off, copy, delete, grant and run an
automation by hand, and the assistant's drafts (WORKBOOK FLOW-F03 to F19). The engine's own tests are
``test_services_engine.py``.

Other apps are the real ones: the task an automation creates is a row of ``task_task``.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pydantic
import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.flow.models import Draft, Flow, FlowRun
from apps.task.models import Task

from .conftest import TASK_STEP, ctx_for, make_draft, make_flow, make_run, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)


def events(name: str | None = None) -> list[OutboxEvent]:
    rows = OutboxEvent.objects.order_by("created_at", "id")
    return list(rows.filter(name=name) if name else rows)


# Create (FLOW-F09, F04)


def test_a_new_automation_is_paused_ungranted_and_says_so():
    created = run(
        "flow.flow.create",
        {
            "name": "Welcome",
            "trigger": {"kind": "event", "event": "customer.customer.created"},
            "steps": [TASK_STEP],
        },
        ctx_for(actor="ana", language="es"),
    )
    assert (created.name, created.enabled, created.grants, created.version) == (
        "Welcome",
        False,
        [],
        1,
    )
    assert created.missing_grants == ["task.task.create"]
    assert created.created_by == "ana"
    flow = Flow.objects.get(pk=created.id)
    assert flow.language == "es"
    assert flow.trigger_event == "customer.customer.created"
    assert flow.steps == [TASK_STEP | {"params": {"title": "Welcome the new customer"}}]
    assert "task.task.create" in flow.search_text
    assert [(e.name, e.payload) for e in events()] == [
        ("flow.flow.created", {"id": str(flow.id)})
    ]


def test_without_a_name_it_is_untitled_in_the_callers_language():
    assert run("flow.flow.create", {"name": "  "}).name == "Untitled automation"
    assert (
        run("flow.flow.create", {}, ctx_for(language="es")).name
        == "Automatización sin nombre"
    )


def test_what_the_business_does_not_have_is_refused_by_field():
    with pytest.raises(InvalidPayload) as refused:
        run(
            "flow.flow.create",
            {
                "trigger": {"kind": "event", "event": "spa.sauna.heated"},
                "steps": [
                    TASK_STEP | {"operation": "spa.sauna.heat"},
                    {
                        "id": "s2",
                        "kind": "command",
                        "operation": "customer.customer.detail",
                    },
                    {"id": "s3", "kind": "query", "operation": "task.task.create"},
                    {
                        "id": "s4",
                        "kind": "command",
                        "operation": "task.task.release_member",
                    },
                ],
            },
        )
    assert refused.value.fields == {
        "trigger.event": "That does not happen in this business: «spa.sauna.heated».",
        "steps.0.operation": "That action does not exist in this business: «spa.sauna.heat».",
        "steps.1.operation": "«customer.customer.detail» only reads: use «Look something up».",
        "steps.2.operation": "«task.task.create» changes data: use «Do something».",
        "steps.3.operation": "That action does not exist in this business: «task.task.release_member».",
    }
    assert Flow.objects.count() == 0


def test_a_date_that_has_passed_is_refused(clock):
    clock(NOON)
    with pytest.raises(InvalidPayload) as refused:
        run(
            "flow.flow.create",
            {"trigger": {"kind": "at", "at": "2026-10-15T11:00:00+02:00"}},
        )
    assert refused.value.fields == {
        "trigger.at": "That date and time has already passed."
    }


def test_an_automation_on_a_schedule_or_a_date_knows_when_it_starts_once_on(clock):
    clock(NOON)
    daily = run("flow.flow.create", {"trigger": {"kind": "schedule", "every": "day", "time": "09:00"}})
    assert (daily.enabled, daily.next_fire_at) == (False, None)
    daily = run("flow.flow.set_enabled", {"id": str(daily.id), "enabled": True})
    assert daily.next_fire_at == dt.datetime(2026, 10, 16, 9, 0, tzinfo=MADRID)
    once = run("flow.flow.create", {"trigger": {"kind": "at", "at": "2026-10-20T10:00:00+02:00"}})
    once = run("flow.flow.set_enabled", {"id": str(once.id), "enabled": True})
    assert once.next_fire_at == dt.datetime(2026, 10, 20, 10, 0, tzinfo=MADRID)
    assert [e.name for e in events() if e.payload.get("id") == str(daily.id)] == [
        "flow.flow.created",
        "flow.flow.enabled",
    ]


def test_a_draft_becomes_the_automation_in_the_same_step():
    draft = make_draft()
    created = run(
        "flow.flow.create",
        {"name": "Call them", "steps": [TASK_STEP], "draft_id": str(draft.id)},
        ctx_for(actor="ana"),
    )
    draft.refresh_from_db()
    assert (draft.status, draft.flow_id, draft.decided_by) == (
        Draft.Status.USED,
        created.id,
        "ana",
    )
    assert draft.decided_at is not None
    assert ("flow.draft.used", {"id": str(draft.id), "flow_id": str(created.id)}) in [
        (e.name, e.payload) for e in events()
    ]
    # A draft is decided once: the same review saved twice does not create two automations.
    with pytest.raises(Conflict) as refused:
        run("flow.flow.create", {"name": "Again", "draft_id": str(draft.id)})
    assert refused.value.code == "flow.draft_decided"
    assert Flow.objects.count() == 1


def test_only_who_manages_creates():
    with pytest.raises(PermissionDenied):
        run("flow.flow.create", {}, ctx_for("hub_manager"))
    with pytest.raises(PermissionDenied):
        run("flow.flow.create", {}, ctx_for(permissions={"flow.view"}))


# Update (FLOW-F10, F11, F14)


def test_saving_the_trigger_or_the_steps_raises_the_version():
    flow = make_flow(grants=["task.task.create"])
    saved = run(
        "flow.flow.update",
        {
            "id": str(flow.id),
            "name": "Welcome them",
            "steps": [TASK_STEP, TASK_STEP | {"id": "s2"}],
        },
        ctx_for(actor="luis", language="es"),
    )
    assert (saved.name, saved.version, saved.updated_by) == ("Welcome them", 2, "luis")
    # The permissions it holds stay as they were.
    assert saved.grants == ["task.task.create"]
    assert Flow.objects.get(pk=flow.pk).language == "es"
    assert ("flow.flow.updated", {"id": str(flow.id), "version": 2}) in [
        (e.name, e.payload) for e in events()
    ]
    renamed = run("flow.flow.update", {"id": str(flow.id), "name": "Hello"})
    assert renamed.version == 2


def test_an_update_checks_the_document_against_the_business():
    flow = make_flow()
    with pytest.raises(InvalidPayload) as refused:
        run(
            "flow.flow.update",
            {
                "id": str(flow.id),
                "trigger": {"kind": "event", "event": "spa.sauna.heated"},
            },
        )
    assert set(refused.value.fields) == {"trigger.event"}
    # Data no earlier step leaves is the schema's 422, as on create (test_schemas.py).
    with pytest.raises(pydantic.ValidationError):
        run(
            "flow.flow.update",
            {
                "id": str(flow.id),
                "steps": [TASK_STEP | {"params": {"title": "steps.s9.id"}}],
            },
        )
    assert Flow.objects.get(pk=flow.pk).version == 1


def test_a_schedule_keeps_its_clock_unless_it_changes(clock):
    clock(NOON)
    flow = make_flow(
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
        next_fire_at=dt.datetime(2026, 10, 16, 9, 0, tzinfo=MADRID),
    )
    run("flow.flow.update", {"id": str(flow.id), "name": "Morning"})
    assert Flow.objects.get(pk=flow.pk).next_fire_at == dt.datetime(
        2026, 10, 16, 9, 0, tzinfo=MADRID
    )
    run(
        "flow.flow.update",
        {
            "id": str(flow.id),
            "trigger": {"kind": "schedule", "every": "day", "time": "13:00"},
        },
    )
    assert Flow.objects.get(pk=flow.pk).next_fire_at == dt.datetime(
        2026, 10, 15, 13, 0, tzinfo=MADRID
    )


def test_an_automation_is_changed_by_its_name_too():
    make_flow("Welcome")
    assert run("flow.flow.update", {"flow": "welcome", "name": "Hello"}).name == "Hello"


# On and off (FLOW-F03)


def test_turning_on_a_schedule_counts_from_now_and_pausing_forgets_its_clock(clock):
    flow = make_flow(
        enabled=False,
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
    )
    clock(NOON)
    on = run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": True})
    assert (on.enabled, on.next_fire_at) == (
        True,
        dt.datetime(2026, 10, 16, 9, 0, tzinfo=MADRID),
    )
    off = run("flow.flow.set_enabled", {"flow": flow.name, "enabled": False})
    assert (off.enabled, off.next_fire_at) == (False, None)
    assert [e.name for e in events()] == ["flow.flow.enabled", "flow.flow.paused"]


def test_turning_on_what_is_already_on_says_nothing():
    flow = make_flow(enabled=True)
    run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": True})
    assert events() == []


# Copy (FLOW-F06)


def test_a_copy_is_paused_ungranted_and_numbered():
    flow = make_flow("Welcome", grants=["task.task.create"])
    make_run(flow)
    first = run("flow.flow.duplicate", {"id": str(flow.id)})
    second = run("flow.flow.duplicate", {"id": str(flow.id)})
    assert (first.name, first.enabled, first.grants, first.last_run) == (
        "Copy of Welcome",
        False,
        [],
        None,
    )
    assert second.name == "Copy of Welcome (2)"
    assert first.steps == flow.steps and first.trigger == {
        "kind": "event",
        "event": "customer.customer.created",
        "filter": {},
    }
    in_spanish = run(
        "flow.flow.duplicate", {"id": str(flow.id)}, ctx_for(language="es")
    )
    assert in_spanish.name == "Copia de Welcome"


# Delete (FLOW-F07)


def test_deleting_stops_it_cancels_what_waited_and_keeps_its_history(clock):
    clock(NOON)
    flow = make_flow()
    done = make_run(flow)
    waiting = make_run(
        flow, status=FlowRun.Status.WAITING, resume_at=NOON + dt.timedelta(hours=1)
    )
    deleted = run("flow.flow.delete", {"id": str(flow.id)})
    assert deleted.id == flow.id
    flow.refresh_from_db()
    assert flow.deleted_at == NOON and flow.enabled is False
    waiting.refresh_from_db()
    assert (waiting.status, waiting.error_code, waiting.finished_at) == (
        FlowRun.Status.CANCELLED,
        "flow.deleted",
        NOON,
    )
    assert FlowRun.objects.get(pk=done.pk).status == FlowRun.Status.SUCCEEDED
    assert [e.name for e in events()] == ["flow.run.finished", "flow.flow.deleted"]
    with pytest.raises(NotFound):
        run("flow.flow.delete", {"id": str(flow.id)})


# Permissions (FLOW-F12)


def test_granting_sets_the_whole_list():
    flow = make_flow(grants=[])
    granted = run(
        "flow.flow.grant",
        {
            "id": str(flow.id),
            "operations": [
                "task.task.create",
                "customer.customer.detail",
                "task.task.create",
            ],
        },
    )
    assert granted.grants == ["task.task.create", "customer.customer.detail"]
    assert granted.missing_grants == []
    withdrawn = run(
        "flow.flow.grant",
        {"id": str(flow.id), "operations": ["customer.customer.detail"]},
    )
    assert withdrawn.missing_grants == ["task.task.create"]
    assert [e.name for e in events()] == ["flow.flow.granted", "flow.flow.granted"]


def test_a_list_that_names_what_does_not_exist_is_refused_whole():
    flow = make_flow(grants=["task.task.create"])
    with pytest.raises(InvalidPayload) as refused:
        run(
            "flow.flow.grant",
            {
                "id": str(flow.id),
                "operations": [
                    "customer.customer.detail",
                    "spa.sauna.heat",
                    "task.task.release_member",
                ],
            },
        )
    assert refused.value.fields == {
        "operations.1": "That action does not exist in this business: «spa.sauna.heat».",
        "operations.2": "That action does not exist in this business: «task.task.release_member».",
    }
    assert Flow.objects.get(pk=flow.pk).grants == ["task.task.create"]


# Run by hand (FLOW-F15)


def test_running_by_hand_does_it_for_real():
    flow = make_flow(
        trigger_kind=Flow.Trigger.MANUAL,
        steps=[TASK_STEP | {"params": {"title": "Call {{input.who}}"}}],
    )
    result = run(
        "flow.flow.run",
        {"id": str(flow.id), "input": {"who": "Ana"}},
        ctx_for(actor="luis"),
    )
    assert (result.status, result.trigger_kind, result.started_by, result.input) == (
        "succeeded",
        "manual",
        "luis",
        {"who": "Ana"},
    )
    assert Task.objects.get().title == "Call Ana"
    assert [e.name for e in events() if e.name.startswith("flow.")] == [
        "flow.run.started",
        "flow.run.finished",
    ]


def test_a_paused_automation_is_not_run_by_hand():
    flow = make_flow(enabled=False)
    with pytest.raises(Conflict) as refused:
        run("flow.flow.run", {"id": str(flow.id)})
    assert refused.value.code == "flow.disabled"
    assert refused.value.message == "This automation is paused: turn it on to run it."
    assert FlowRun.objects.count() == 0


def test_two_runs_by_hand_are_two_runs():
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL)
    run("flow.flow.run", {"id": str(flow.id)})
    run("flow.flow.run", {"id": str(flow.id)})
    assert FlowRun.objects.filter(flow=flow).count() == 2


# The assistant's drafts (FLOW-F17, F19)


def test_the_assistant_leaves_a_draft_that_runs_nothing():
    proposed = run(
        "flow.draft.propose",
        {
            "name": "Task for big sales",
            "definition": {
                "trigger": {"kind": "event", "event": "sale.sale.completed"},
                "steps": [
                    {
                        "id": "s1",
                        "kind": "condition",
                        "when": {"input.total": {"gt": 10000}},
                    },
                    TASK_STEP | {"id": "s2"},
                ],
            },
            "notes": ["I guessed the amount."],
        },
        ctx_for(actor="ana"),
    )
    assert (proposed.status, proposed.flow_id, proposed.created_by) == (
        "pending",
        None,
        "ana",
    )
    assert proposed.definition["trigger"] == {
        "kind": "event",
        "event": "sale.sale.completed",
        "filter": {},
    }
    assert proposed.notes == ["I guessed the amount."]
    assert Flow.objects.count() == 0
    assert [(e.name, e.payload) for e in events()] == [
        ("flow.draft.proposed", {"id": str(proposed.id)})
    ]


def test_a_draft_without_a_trigger_is_by_hand():
    proposed = run(
        "flow.draft.propose", {"name": "Hand", "definition": {"steps": [TASK_STEP]}}
    )
    assert "trigger" not in proposed.definition


def test_dismissing_a_draft_once():
    draft = make_draft()
    dismissed = run("flow.draft.dismiss", {"id": str(draft.id)}, ctx_for(actor="ana"))
    assert (dismissed.status, Draft.objects.get().decided_by) == ("dismissed", "ana")
    assert [e.name for e in events()] == ["flow.draft.dismissed"]
    with pytest.raises(Conflict) as refused:
        run("flow.draft.dismiss", {"id": str(draft.id)})
    assert refused.value.code == "flow.draft_decided"
    with pytest.raises(NotFound):
        run("flow.draft.dismiss", {"id": str(uuid.uuid7())})


def test_the_engine_is_not_for_people():
    for name, data in (
        (
            "flow.run.react",
            {"event_id": str(uuid.uuid7()), "event": "customer.customer.created"},
        ),
        ("flow.schedule.fire_due", {}),
        ("flow.run.resume_due", {}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, ctx_for("hub_owner"))


def test_a_refused_write_leaves_nothing(clock):
    clock(NOON)
    with pytest.raises(InvalidPayload):
        run(
            "flow.flow.create", {"steps": [TASK_STEP | {"operation": "spa.sauna.heat"}]}
        )
    assert (Flow.objects.count(), OutboxEvent.objects.count()) == (0, 0)
    assert timezone.now() == NOON


def test_a_date_that_passed_does_not_block_renaming_or_saving_it_again(clock):
    # Review 2026-10-15, item 4: only a date that changes is checked against now.
    when = dt.datetime(2026, 10, 14, 9, 0, tzinfo=MADRID)
    flow = make_flow(trigger_kind=Flow.Trigger.AT, trigger_event="", run_at=when)
    clock(NOON)
    same = {"kind": "at", "at": when.isoformat()}
    assert run("flow.flow.update", {"id": str(flow.id), "name": "Renamed", "trigger": same}).name == "Renamed"
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.update", {"id": str(flow.id), "trigger": {"kind": "at", "at": "2026-10-15T11:00:00+02:00"}})
    assert refused.value.fields == {"trigger.at": "That date and time has already passed."}
