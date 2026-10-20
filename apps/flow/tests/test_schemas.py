"""Input schemas of the flow app: the document an automation is written in (its trigger and its steps),
what the assistant may propose, and every list's limits. A refusal names the field it belongs to, so the
editor puts it next to the step that has it."""

import datetime as dt

import pydantic
import pytest

from apps.flow import schemas


def errors(schema, data) -> dict[str, str]:
    with pytest.raises(pydantic.ValidationError) as caught:
        schema.model_validate(data)
    return {
        ".".join(map(str, error["loc"])): error["msg"]
        for error in caught.value.errors()
    }


COMMAND = {
    "id": "s1",
    "kind": "command",
    "operation": "task.task.create",
    "params": {"title": "Hi"},
}


# Triggers


def test_the_four_triggers():
    parsed = schemas.CreateIn.model_validate(
        {
            "name": "A",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"input.total": {"gte": 10000}},
            },
        }
    )
    assert parsed.trigger.kind == "event"
    assert parsed.trigger.filter == {"input.total": {"gte": 10000}}
    week = schemas.CreateIn.model_validate(
        {
            "name": "B",
            "trigger": {
                "kind": "schedule",
                "every": "week",
                "weekday": 4,
                "time": "18:00",
            },
        }
    )
    assert (week.trigger.every, week.trigger.weekday, week.trigger.time) == (
        "week",
        4,
        "18:00",
    )
    once = schemas.CreateIn.model_validate(
        {"name": "C", "trigger": {"kind": "at", "at": "2026-11-01T09:00:00+01:00"}}
    )
    assert once.trigger.at == dt.datetime(2026, 11, 1, 8, 0, tzinfo=dt.UTC)
    assert schemas.CreateIn.model_validate({"name": "D"}).trigger.kind == "manual"


def test_an_event_trigger_needs_a_well_formed_event_name():
    found = errors(
        schemas.CreateIn, {"name": "A", "trigger": {"kind": "event", "event": ""}}
    )
    assert found == {
        "trigger.event.event": "Value error, Choose what has to happen for it to start."
    }
    found = errors(
        schemas.CreateIn,
        {"name": "A", "trigger": {"kind": "event", "event": "sale completed"}},
    )
    assert "trigger.event.event" in found


def test_a_schedule_needs_its_day_and_a_valid_time():
    assert errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {"kind": "schedule", "every": "week", "time": "18:00"},
        },
    ) == {"trigger.schedule": "Value error, Choose the day of the week."}
    assert errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {"kind": "schedule", "every": "month", "time": "18:00"},
        },
    ) == {"trigger.schedule": "Value error, Choose the day of the month."}
    assert "trigger.schedule.time" in errors(
        schemas.CreateIn,
        {"name": "A", "trigger": {"kind": "schedule", "every": "day", "time": "25:00"}},
    )
    assert "trigger.schedule.day" in errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {
                "kind": "schedule",
                "every": "month",
                "day": 32,
                "time": "08:00",
            },
        },
    )


def test_a_date_needs_its_offset():
    found = errors(
        schemas.CreateIn,
        {"name": "A", "trigger": {"kind": "at", "at": "2026-11-01T09:00:00"}},
    )
    assert "trigger.at.at" in found


def test_a_condition_needs_a_known_operator_on_a_path():
    assert "trigger.event.filter" in errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"total": {"gte": 1}},
            },
        },
    )
    assert "trigger.event.filter" in errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"input.total": {"bigger": 1}},
            },
        },
    )
    assert "trigger.event.filter" in errors(
        schemas.CreateIn,
        {
            "name": "A",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"input.total": {}},
            },
        },
    )


# Steps


def test_the_four_steps():
    parsed = schemas.CreateIn.model_validate(
        {
            "name": "A",
            "steps": [
                {
                    "id": "s1",
                    "kind": "query",
                    "operation": "customer.customer.detail",
                    "params": {"id": "input.customer_id"},
                },
                {
                    "id": "s2",
                    "kind": "condition",
                    "when": {"steps.s1.found": {"eq": True}},
                },
                {"id": "s3", "kind": "delay", "seconds": 3600},
                COMMAND | {"id": "s4", "params": {"title": "Call {{steps.s1.name}}"}},
            ],
        }
    )
    assert [step.kind for step in parsed.steps] == [
        "query",
        "condition",
        "delay",
        "command",
    ]
    assert parsed.steps[0].result == "first"


def test_a_step_needs_its_action():
    found = errors(
        schemas.CreateIn, {"name": "A", "steps": [COMMAND | {"operation": ""}]}
    )
    assert found == {
        "steps.0.command.operation": "Value error, Choose what this step does."
    }


def test_step_ids_are_unique_and_well_formed():
    assert errors(schemas.CreateIn, {"name": "A", "steps": [COMMAND, COMMAND]}) == {
        "steps": "Value error, Two steps have the id «s1»."
    }
    assert "steps.0.command.id" in errors(
        schemas.CreateIn, {"name": "A", "steps": [COMMAND | {"id": "Step 1"}]}
    )


def test_a_step_reads_only_what_an_earlier_step_left():
    later = [
        COMMAND | {"params": {"title": "steps.s2.id"}},
        COMMAND | {"id": "s2"},
    ]
    assert errors(schemas.CreateIn, {"name": "A", "steps": later}) == {
        "steps": "Value error, Step 1 reads «steps.s2.id», which no earlier step leaves."
    }
    after_a_condition = [
        {"id": "s1", "kind": "condition", "when": {"input.total": {"gt": 1}}},
        COMMAND | {"id": "s2", "params": {"title": "{{steps.s1.x}}"}},
    ]
    assert "steps" in errors(
        schemas.CreateIn, {"name": "A", "steps": after_a_condition}
    )


def test_a_condition_compares_only_with_data_it_already_has():
    # hub#1712: the second datum of a comparison is a reference like any other.
    later = [
        {"id": "s1", "kind": "condition", "when": {"input.total": {"gt": "steps.s2.total"}}},
        COMMAND | {"id": "s2"},
    ]
    assert errors(schemas.CreateIn, {"name": "A", "steps": later}) == {
        "steps": "Value error, Step 1 reads «steps.s2.total», which no earlier step leaves."
    }
    earlier = [
        COMMAND,
        {"id": "s2", "kind": "condition", "when": {"input.total": {"gt": "steps.s1.total"}}},
    ]
    schemas.CreateIn.model_validate({"name": "A", "steps": earlier})


def test_a_template_reads_only_paths():
    found = errors(
        schemas.CreateIn,
        {"name": "A", "steps": [COMMAND | {"params": {"title": "Hi {{foo}}"}}]},
    )
    assert found == {
        "steps": "Value error, Step 1 reads «foo», which is no data of this automation."
    }


def test_a_wait_is_one_minute_to_thirty_days():
    for seconds in (59, 30 * 24 * 3600 + 1):
        assert "steps.0.delay.seconds" in errors(
            schemas.CreateIn,
            {"name": "A", "steps": [{"id": "s1", "kind": "delay", "seconds": seconds}]},
        )


def test_at_most_fifty_steps():
    steps = [{"id": f"s{n}", "kind": "delay", "seconds": 60} for n in range(51)]
    assert "steps" in errors(schemas.CreateIn, {"name": "A", "steps": steps})


def test_an_unknown_step_kind_is_refused():
    assert "steps.0" in errors(
        schemas.CreateIn,
        {"name": "A", "steps": [{"id": "s1", "kind": "http", "url": "x"}]},
    )


def test_document_problems_is_what_an_update_checks_too():
    problems = schemas.document_problems(
        [schemas.CommandStep.model_validate(COMMAND | {"params": {"title": "steps.s9.id"}})]
    )
    assert problems == ["Step 1 reads «steps.s9.id», which no earlier step leaves."]


# The assistant's draft: narrower than what a person builds


def test_a_draft_proposes_commands_conditions_and_waits_only():
    ok = schemas.DraftProposeIn.model_validate(
        {
            "name": "Call who did not come",
            "definition": {
                "trigger": {
                    "kind": "event",
                    "event": "appointment.appointment.marked_no_show",
                },
                "steps": [COMMAND],
            },
            "notes": ["I guessed the priority."],
        }
    )
    assert ok.definition.steps[0].operation == "task.task.create"
    query = {"id": "s1", "kind": "query", "operation": "customer.customer.detail"}
    assert "definition.steps.0" in errors(
        schemas.DraftProposeIn,
        {"name": "A", "definition": {"steps": [query]}, "notes": []},
    )


def test_a_draft_has_one_to_eight_steps_and_at_most_eight_notes():
    assert "definition.steps" in errors(
        schemas.DraftProposeIn, {"name": "A", "definition": {"steps": []}, "notes": []}
    )
    nine = [COMMAND | {"id": f"s{n}"} for n in range(9)]
    assert "definition.steps" in errors(
        schemas.DraftProposeIn,
        {"name": "A", "definition": {"steps": nine}, "notes": []},
    )
    assert "notes" in errors(
        schemas.DraftProposeIn,
        {"name": "A", "definition": {"steps": [COMMAND]}, "notes": ["x"] * 9},
    )


# References, lists and the rest


def test_a_flow_is_named_by_its_id_or_its_name():
    assert schemas.FlowRefIn.model_validate({"flow": "welcome"}).flow == "welcome"
    assert errors(schemas.FlowRefIn, {}) == {
        "flow": "Value error, Say which automation: its id or its name."
    }


def test_lists_take_at_most_100_rows_and_refuse_unknown_filters():
    assert "limit" in errors(schemas.FlowListIn, {"limit": 101})
    assert "colour" in errors(schemas.FlowListIn, {"colour": "red"})
    assert schemas.FlowListIn.model_validate({}).sort == "-updated_at"
    assert (
        schemas.RunListIn.model_validate(
            {"flow_id": "0199e7a0-0000-7000-8000-000000000000"}
        ).limit
        == 20
    )


def test_a_manual_run_takes_its_input():
    parsed = schemas.RunIn.model_validate(
        {"flow": "Welcome", "input": {"customer_id": "c-1"}}
    )
    assert parsed.input == {"customer_id": "c-1"}


def test_the_name_is_trimmed_and_at_most_120_characters():
    assert schemas.CreateIn.model_validate({"name": "  Welcome  "}).name == "Welcome"
    assert "name" in errors(schemas.CreateIn, {"name": "x" * 121})


def test_turning_on_is_only_set_enabled_s_which_the_assistant_confirms():
    # Review 2026-10-15, item 3: create and update carry no switch.
    assert "enabled" in errors(schemas.CreateIn, {"name": "A", "enabled": True})
    assert "enabled" in errors(schemas.UpdateIn, {"flow": "A", "enabled": True})


def test_a_draft_reads_only_what_its_earlier_steps_leave():
    # Review 2026-10-15, item 10: the same check as a person's document.
    later = [COMMAND | {"params": {"title": "steps.s2.id"}}, COMMAND | {"id": "s2"}]
    found = errors(schemas.DraftProposeIn, {"name": "A", "definition": {"steps": later}, "notes": []})
    assert found == {"definition.steps": "Value error, Step 1 reads «steps.s2.id», which no earlier step leaves."}
