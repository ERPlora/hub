"""Models of the flow app: the automation, its runs and the assistant's drafts (WORKBOOK «Para quien lo
mantiene»). UUIDv7 keys, no hub id; one run per automation and trigger key."""

import pytest
from django.db import IntegrityError, transaction
from live.models import UUIDModel

from apps.flow.models import Draft, Flow, FlowRun

from .conftest import make_draft, make_flow, make_run

pytestmark = pytest.mark.django_db


def test_every_model_has_a_uuid7_key_and_no_hub_id():
    for model in (Flow, FlowRun, Draft):
        assert issubclass(model, UUIDModel), model
        assert "hub_id" not in {field.name for field in model._meta.get_fields()}, model
    assert make_flow().id.version == 7


def test_a_new_flow_is_paused_manual_ungranted_and_at_version_one():
    flow = Flow.objects.create(name="Morning check")
    assert flow.enabled is False
    assert flow.trigger_kind == Flow.Trigger.MANUAL
    assert (flow.steps, flow.grants, flow.trigger_filter, flow.schedule) == (
        [],
        [],
        {},
        {},
    )
    assert flow.version == 1
    assert flow.deleted_at is None
    assert flow.language == "en"
    assert str(flow) == "Morning check"


def test_the_trigger_and_run_choices():
    assert Flow.Trigger.values == ["event", "schedule", "at", "manual"]
    assert FlowRun.Status.values == [
        "running",
        "waiting",
        "calling",
        "asking",
        "succeeded",
        "stopped",
        "failed",
        "cancelled",
    ]
    assert Draft.Status.values == ["pending", "used", "dismissed"]


def test_an_event_flow_needs_its_event():
    with pytest.raises(IntegrityError), transaction.atomic():
        Flow.objects.create(
            name="No event", trigger_kind=Flow.Trigger.EVENT, trigger_event=""
        )


def test_an_unknown_trigger_kind_is_refused_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        Flow.objects.create(name="Odd", trigger_kind="sometimes")


def test_an_automation_of_its_own_comes_from_no_recipe():
    flow = Flow.objects.create(name="Mine")
    assert (flow.recipe, flow.recipe_digest) == ("", "")


def test_one_automation_per_recipe_while_it_is_not_deleted():
    # FLOW-F33: turning a recipe on twice is one automation; a deleted one lets it be built again.
    first = make_flow(recipe="appointment/customer_cancelled", recipe_digest="a" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_flow("Again", recipe="appointment/customer_cancelled", recipe_digest="a" * 64)
    make_flow("Another recipe", recipe="online_booking/booked_online")
    make_flow("Mine"), make_flow("Mine too")  # automations of the owner's own come from no recipe
    first.deleted_at = first.created_at
    first.save(update_fields=["deleted_at"])
    make_flow("Built again", recipe="appointment/customer_cancelled")


def test_one_run_per_flow_and_trigger_key():
    flow = make_flow()
    make_run(flow, trigger_key="event-1")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_run(flow, trigger_key="event-1")
    # Another automation may run on the same event.
    make_run(make_flow("Other"), trigger_key="event-1")


def test_a_run_remembers_the_version_and_steps_it_started_with():
    flow = make_flow(version=3)
    run = make_run(flow)
    assert run.flow_version == 3
    assert run.definition == {"steps": flow.steps}
    assert (run.log, run.outputs, run.chain, run.input) == ([], {}, [], {})
    assert run.step_index == 0
    assert run.started_at is not None and run.finished_at is None


def test_an_unknown_run_status_is_refused_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        make_run(make_flow(), status="lost")


def test_runs_are_newest_first():
    flow = make_flow()
    first = make_run(flow)
    second = make_run(flow)
    assert list(FlowRun.objects.filter(flow=flow)) == [second, first]


def test_a_draft_is_born_pending_and_points_at_nothing():
    draft = make_draft()
    assert draft.status == Draft.Status.PENDING
    assert draft.flow is None
    assert draft.notes == []
    assert str(draft) == "Call who did not come"


def test_deleting_a_flow_row_keeps_its_drafts_and_removes_its_runs():
    flow = make_flow()
    make_run(flow)
    draft = make_draft(status=Draft.Status.USED, flow=flow)
    flow.delete()
    assert FlowRun.objects.count() == 0
    draft.refresh_from_db()
    assert draft.flow is None
